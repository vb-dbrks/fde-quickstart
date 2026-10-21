"""The app side of the agent handoff (ADR 0003, ADR 0004).

``start_run``   builds the full-context request, stores an ``agent_runs`` row, submits it.
``refresh_run`` polls the agent for a non-terminal run, then - with the row locked and re-read -
                mirrors the status into the row and, on the first ``succeeded``, materialises the
                output in one transaction, so the UI's lazy refresh, the background poller and other
                app instances can't double-apply it. No lock or connection is held while the agent
                is called.

Run kinds and what "materialise" means for each:

  generate        write the fields, snapshot a version, audit (services/materialise.py)
  enhance_field   nothing; the suggestion waits in ``response_payload`` until the user accepts it
  assistant_turn  store the assistant's reply in the thread
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.access import require_document
from backend.auth.principal import Principal
from backend.auth.roles import Permission
from backend.contracts.agent_contract_v1 import AgentRunKind, AgentRunStatus
from backend.contracts.field_catalog import FieldCatalog
from backend.domain.enums import Access, RunStatus
from backend.domain.errors import ForbiddenError, InvalidInputError, NotFoundError
from backend.domain.models import AgentRun, Document, Message, new_id
from backend.services import assistant, documents
from backend.services.agent_client import (
    AgentClient,
    AgentClientError,
    AgentContractError,
    AgentRemoteError,
    AgentRunNotFound,
)
from backend.services.agent_payload_builder import build_request, render_source
from backend.services.materialise import MaterialisationError, materialise_generate
from backend.services.notification_channels import Message as Notice
from backend.services.notifications import Notifier
from backend.settings import Settings

logger = logging.getLogger(__name__)

MAX_SOURCES = 5
RUN_LABELS = {"generate": "Generate", "enhance_field": "Enhance", "assistant_turn": "Assistant"}


@dataclass(frozen=True)
class RunOptions:
    run_kind: AgentRunKind
    instruction: str | None = None
    scope: list[str] | None = None
    field_path: str | None = None
    thread_id: str | None = None
    message: str | None = None
    source_document_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RunDeps:
    client: AgentClient
    catalog: FieldCatalog
    settings: Settings
    notifier: Notifier


def _now() -> datetime:
    return datetime.now(UTC)


def queued_grace(settings: Settings) -> timedelta:
    """How long a run may stay ``queued`` before it is failed as ORPHANED. Longer than the slowest
    submit (the HTTP client tries three times, each up to the request timeout), so the poller never
    gives up on a run whose submit is still in flight."""
    return timedelta(seconds=max(60.0, 4 * settings.agent_request_timeout_seconds))


def visible_runs(principal: Principal) -> ColumnElement[bool]:
    """Chat runs are private to whoever started them; other runs follow the document's access."""
    return (AgentRun.run_kind != "assistant_turn") | (AgentRun.triggered_by == principal.email)


async def _lock_run(db: AsyncSession, run_id: str) -> AgentRun | None:
    """The run, locked FOR UPDATE and re-read from the database. ``populate_existing`` matters: the
    session may already hold this run from before the lock (it keeps objects across commits), and
    without it the lock would hand back those stale values."""
    query = (
        select(AgentRun)
        .where(AgentRun.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    run: AgentRun | None = await db.scalar(query)
    return run


def _apply_status(run: AgentRun, status: AgentRunStatus) -> None:
    run.status = status.status
    run.step_history = [step.model_dump(mode="json") for step in status.step_history]
    run.mlflow_trace_id = status.trace_id or run.mlflow_trace_id
    if status.status in ("succeeded", "failed"):
        run.response_payload = status.model_dump(mode="json", exclude_none=True)
        run.completed_at = _now()
    if status.error is not None:
        run.error_code = status.error.code
        run.error_message = status.error.message


def _fail(run: AgentRun, code: str, message: str) -> None:
    run.status = RunStatus.FAILED.value
    run.error_code = code
    run.error_message = message
    run.completed_at = _now()


def _validate(
    options: RunOptions, document: Document, access: Access, catalog: FieldCatalog
) -> None:
    doc_type = documents.document_type(catalog, document.document_type)
    if options.run_kind in ("generate", "enhance_field") and not access.allows(Access.EDIT):
        raise ForbiddenError("This needs edit access to the document")
    if options.run_kind == "enhance_field":
        spec = doc_type.field(options.field_path or "")
        if spec is None or not spec.agent_generates:
            raise InvalidInputError("Choose a field the agent can write")
    if options.run_kind == "generate" and options.scope:
        unknown = [
            p for p in options.scope if (s := doc_type.field(p)) is None or not s.agent_generates
        ]
        if unknown:
            raise InvalidInputError(f"Not agent fields: {', '.join(unknown)}")
    if options.run_kind == "assistant_turn" and not (
        options.thread_id and (options.message or "").strip()
    ):
        raise InvalidInputError("An assistant turn needs a conversation and a message")


async def start_run(
    db: AsyncSession,
    deps: RunDeps,
    principal: Principal,
    document: Document,
    access: Access,
    options: RunOptions,
    *,
    idempotency_key: str | None = None,
) -> AgentRun:
    if not principal.can(Permission.AGENTS_RUN):
        raise ForbiddenError(f"Missing permission: {Permission.AGENTS_RUN}")
    _validate(options, document, access, deps.catalog)

    fields = documents.field_values(await documents.field_rows(db, document.id))
    source_ids = [i for i in options.source_document_ids if i != document.id][:MAX_SOURCES]
    sources = [
        render_source(
            source, documents.field_values(await documents.field_rows(db, source.id)), deps.catalog
        )
        for source in await documents.accessible_documents(db, principal, source_ids)
    ]
    history: list[tuple[str, str]] = []
    truncated = False
    thread_id = None
    if options.run_kind == "assistant_turn":
        thread = await assistant.require_thread(db, principal, options.thread_id or "")
        if thread.document_id != document.id:
            raise InvalidInputError("That conversation belongs to another document")
        thread_id = thread.id
        history, truncated = await assistant.recent_history(
            db, thread.id, limit=deps.settings.assistant_history_limit
        )

    run_id = new_id()
    request = build_request(
        run_id=run_id,
        run_kind=options.run_kind,
        document=document,
        fields=fields,
        initiator=principal.email,
        idempotency_key=idempotency_key,
        instruction=options.instruction,
        scope=options.scope,
        field_path=options.field_path,
        thread_id=thread_id,
        message=options.message,
        history=history,
        history_truncated=truncated,
        sources=sources,
    )
    run = AgentRun(
        id=run_id,
        document_id=document.id,
        thread_id=thread_id,
        run_kind=options.run_kind,
        status=RunStatus.QUEUED.value,
        triggered_by=principal.email,
        request_payload=request.model_dump(mode="json", exclude_none=True),
        step_history=[],
    )
    db.add(run)
    if thread_id is not None:
        db.add(
            Message(
                thread_id=thread_id,
                role="user",
                content=(options.message or "").strip(),
                citations=[],
                agent_run_id=run_id,
            )
        )
    # The run exists even if the submit below fails, and no transaction is open during the submit.
    await db.commit()

    status: AgentRunStatus | None = None
    try:
        status = await deps.client.submit(request)
    except AgentClientError as exc:
        logger.warning("Submitting agent run %s failed: %s", run_id, exc)
    locked = await _lock_run(db, run_id)
    assert locked is not None
    if locked.status != RunStatus.QUEUED:
        # The poller already gave up on it (ORPHANED) while the submit was in flight: leave it.
        logger.warning("Run %s was %s before its submit returned", run_id, locked.status)
    elif status is None:
        _fail(locked, "SUBMIT_FAILED", "The agent could not accept the run. Try again.")
        await _notify_failure(db, deps, locked, document)
    else:
        _apply_status(locked, status)
        locked.submitted_at = _now()
    await db.commit()
    return locked


@dataclass(frozen=True)
class _PollOutcome:
    status: AgentRunStatus | None = None
    failure: tuple[str, str] | None = None  # (error code, message)


async def _poll(deps: RunDeps, run_id: str) -> _PollOutcome:
    try:
        return _PollOutcome(status=await deps.client.poll(run_id))
    except AgentRunNotFound:
        return _PollOutcome(
            failure=("AGENT_RUN_LOST", "The agent restarted and lost this run. Try again.")
        )
    except AgentContractError as exc:
        return _PollOutcome(
            failure=("CONTRACT_ERROR", f"The agent's response broke the contract: {exc}")
        )
    except AgentRemoteError as exc:
        if not exc.retryable:
            return _PollOutcome(failure=(exc.code, exc.message))
        logger.info("Polling run %s failed, will retry: %s", run_id, exc)
    except AgentClientError as exc:  # timeouts and anything else transient
        logger.info("Polling run %s failed, will retry: %s", run_id, exc)
    return _PollOutcome()


async def refresh_run(db: AsyncSession, deps: RunDeps, run_id: str) -> AgentRun | None:
    """Bring a run up to date with the agent. Safe to call concurrently and repeatedly.

    1. Read the run; stop if it is already terminal.
    2. Poll the agent with no transaction open, so no lock or pooled connection waits on it.
    3. Lock the row, re-read it and check again - another request may have finished the run in the
       meantime - then apply the outcome and materialise in one transaction.
    """
    run = await db.get(AgentRun, run_id, populate_existing=True)
    if run is None or RunStatus(run.status).terminal:
        await db.commit()
        return run
    deadline = run.created_at + timedelta(seconds=deps.settings.agent_run_timeout_seconds)
    polled = run.status != RunStatus.QUEUED and _now() < deadline
    outcome = _PollOutcome()
    if polled:
        await db.commit()
        outcome = await _poll(deps, run_id)

    run = await _lock_run(db, run_id)
    if run is None or RunStatus(run.status).terminal:
        await db.commit()
        return run
    document = await db.get(Document, run.document_id, populate_existing=True)
    if run.status == RunStatus.QUEUED:
        if run.created_at < _now() - queued_grace(deps.settings):
            _fail(run, "ORPHANED", "The run was never accepted by the agent.")
            await _notify_failure(db, deps, run, document)
        await db.commit()
        return run
    if _now() >= deadline:
        _fail(run, "TIMEOUT", "The agent took too long.")
        await _notify_failure(db, deps, run, document)
        await db.commit()
        return run

    if polled:
        run.last_polled_at = _now()
    if outcome.failure is not None:
        _fail(run, *outcome.failure)
    elif outcome.status is not None:
        status = outcome.status
        _apply_status(run, status)
        if status.status == "succeeded" and status.output is not None and document is not None:
            await _materialise(db, deps, run, document, status)

    if run.status == RunStatus.FAILED:
        await _notify_failure(db, deps, run, document)
    elif run.status == RunStatus.SUCCEEDED and run.run_kind == "generate" and document is not None:
        await deps.notifier.notify(
            db,
            Notice(
                recipient=run.triggered_by,
                kind="agent_run_succeeded",
                title=f"Generate finished for “{document.title}”",
                body="Review the drafted fields.",
                link=f"/documents/{document.id}",
            ),
        )
    await db.commit()
    return run


async def _materialise(
    db: AsyncSession, deps: RunDeps, run: AgentRun, document: Document, status: AgentRunStatus
) -> None:
    assert status.output is not None
    try:
        if run.run_kind == "generate":
            await materialise_generate(
                db,
                run=run,
                document=document,
                output=status.output,
                catalog=deps.catalog,
                trace_id=status.trace_id,
            )
        elif run.run_kind == "assistant_turn":
            await assistant.finalize_assistant_turn(db, run=run, output=status.output)
    except MaterialisationError as exc:
        logger.warning("Materialising run %s failed: %s", run.id, exc)
        _fail(run, MaterialisationError.code, str(exc))


async def _notify_failure(
    db: AsyncSession, deps: RunDeps, run: AgentRun, document: Document | None
) -> None:
    title = document.title if document else "a document"
    label = RUN_LABELS.get(run.run_kind, run.run_kind)
    await deps.notifier.notify(
        db,
        Notice(
            recipient=run.triggered_by,
            kind="agent_run_failed",
            title=f"{label} failed for “{title}”",
            body=run.error_message,
            link=f"/documents/{run.document_id}",
        ),
    )


async def get_run_for(
    db: AsyncSession, principal: Principal, run_id: str
) -> tuple[AgentRun, Document]:
    """A run the principal may see: view access to its document; chat runs only for their owner."""
    run = await db.scalar(select(AgentRun).where(AgentRun.id == run_id, visible_runs(principal)))
    if run is None:
        raise NotFoundError("Run not found")
    document, _ = await require_document(db, principal, run.document_id, Access.VIEW)
    return run, document


async def recent_runs(db: AsyncSession, principal: Principal, document_id: str) -> list[AgentRun]:
    query = (
        select(AgentRun)
        .where(AgentRun.document_id == document_id, visible_runs(principal))
        .order_by(AgentRun.created_at.desc())
        .limit(20)
    )
    return list((await db.scalars(query)).all())


def run_kind(value: str) -> AgentRunKind:
    return cast(AgentRunKind, value)
