"""Application-owned execution, durable AG-UI events and recovery. No example imports."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from ag_ui.core import (
    AssistantMessage,
    EventType,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StateSnapshotEvent,
    UserMessage,
)
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.principal import Principal
from backend.auth.roles import Permission
from backend.contracts.execution import ExecutionRequest
from backend.domain.errors import ConflictError, ForbiddenError, InvalidInputError, NotFoundError
from backend.domain.models import AgentRun, Message, RunEvent, Thread, new_id
from backend.services.agent_client import AgentClient, AgentClientError, AgentRunNotFound

Authorize = Callable[[AsyncSession, Principal, AgentRun], Awaitable[None]]
Prepare = Callable[[AsyncSession, Principal, dict[str, Any]], Awaitable[dict[str, Any]]]
Finalize = Callable[[AsyncSession, AgentRun, dict[str, Any]], Awaitable[None]]
ReviewState = Callable[[AsyncSession, AgentRun], Awaitable[dict[str, Any]]]
Review = Callable[[AsyncSession, Principal, AgentRun, dict[str, Any]], Awaitable[dict[str, Any]]]


async def owner_access(db: AsyncSession, principal: Principal, run: AgentRun) -> None:
    if run.triggered_by != principal.email:
        raise NotFoundError("Run not found")


async def empty_context(
    db: AsyncSession, principal: Principal, payload: dict[str, Any]
) -> dict[str, Any]:
    return {}


async def no_finalization(db: AsyncSession, run: AgentRun, result: dict[str, Any]) -> None:
    return None


@dataclass(frozen=True)
class AgentApplication:
    example: str
    input_model: type[BaseModel]
    result_model: type[BaseModel]
    authorize: Authorize = owner_access
    prepare: Prepare = empty_context
    finalize: Finalize = no_finalization
    review: Review | None = None
    review_state: ReviewState | None = None
    tools: dict[str, type[BaseModel]] = field(default_factory=dict)
    execution_version: str = "v2"


async def require_run(
    db: AsyncSession, principal: Principal, run_id: str, applications: dict[str, AgentApplication]
) -> AgentRun:
    run = await db.get(AgentRun, run_id)
    if run is None or run.agent_id not in applications:
        raise NotFoundError("Run not found")
    await applications[run.agent_id].authorize(db, principal, run)
    return run


def append_event(db: AsyncSession, run: AgentRun, event: dict[str, Any]) -> None:
    run.event_count = (run.event_count or 0) + 1
    db.add(RunEvent(run_id=run.id, sequence=run.event_count, event=event))


def event_json(event: BaseModel) -> dict[str, Any]:
    return event.model_dump(mode="json", by_alias=True, exclude_none=True)


def begin_events(db: AsyncSession, run: AgentRun) -> None:
    if not run.event_count:
        append_event(
            db,
            run,
            event_json(
                RunStartedEvent(
                    type=EventType.RUN_STARTED, run_id=run.id, thread_id=run.thread_id or run.id
                )
            ),
        )


def end_events(db: AsyncSession, run: AgentRun) -> None:
    if run.status == "failed":
        event: BaseModel = RunErrorEvent(
            type=EventType.RUN_ERROR,
            message=run.error_message or "Agent failed",
            code=run.error_code,
        )
    else:
        event = RunFinishedEvent(
            type=EventType.RUN_FINISHED, run_id=run.id, thread_id=run.thread_id or run.id
        )
    append_event(db, run, event_json(event))


async def start(
    db: AsyncSession,
    client: AgentClient,
    principal: Principal,
    agent_id: str,
    payload: dict[str, Any],
    thread_id: str | None,
    applications: dict[str, AgentApplication],
) -> AgentRun:
    if not principal.can(Permission.AGENTS_RUN):
        raise ForbiddenError("Missing permission: agents:run")
    application = applications.get(agent_id)
    if application is None:
        raise NotFoundError("Agent not enabled")
    if application.execution_version != "v2":
        raise InvalidInputError("Use this example's compatibility submission route")
    try:
        clean = application.input_model.model_validate(payload).model_dump(mode="json")
    except ValidationError as exc:
        raise InvalidInputError(str(exc)) from exc
    history: list[Any] = []
    if thread_id:
        thread = await db.get(Thread, thread_id, with_for_update=True)
        if thread is None or thread.owner != principal.email or thread.agent_id != agent_id:
            raise NotFoundError("Session not found")
        active = await db.scalar(
            select(AgentRun.id).where(
                AgentRun.thread_id == thread_id,
                AgentRun.status.in_(("queued", "accepted", "running")),
            )
        )
        if active:
            raise ConflictError("A response is already in progress")
        rows = list(
            (
                await db.scalars(
                    select(Message)
                    .where(Message.thread_id == thread_id)
                    .order_by(Message.id.desc())
                    .limit(20)
                )
            ).all()
        )
        for m in reversed(rows):
            message_type = UserMessage if m.role == "user" else AssistantMessage
            history.append(message_type(id=str(m.id), content=m.content))
    run_id = new_id()
    context = await application.prepare(db, principal, clean)
    request = ExecutionRequest(
        run_id=run_id,
        agent_id=agent_id,
        thread_id=thread_id or run_id,
        initiator=principal.email,
        input=clean,
        context=context,
        messages=history,
    )
    run = AgentRun(
        id=run_id,
        agent_id=agent_id,
        contract_version="v2",
        run_kind=agent_id,
        thread_id=thread_id,
        status="queued",
        triggered_by=principal.email,
        request_payload=request.model_dump(mode="json"),
        step_history=[],
        event_count=0,
    )
    db.add(run)
    await application.authorize(db, principal, run)
    if thread_id and isinstance(clean.get("message"), str):
        db.add(
            Message(
                thread_id=thread_id,
                role="user",
                content=clean["message"],
                citations=[],
                agent_run_id=run_id,
            )
        )
    begin_events(db, run)
    await db.commit()
    failed = False
    try:
        await client.submit_execution(request)
    except (ValueError, AgentClientError):
        failed = True
    locked = await db.scalar(
        select(AgentRun)
        .where(AgentRun.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert locked is not None
    run = locked
    if run.status != "queued":
        await db.commit()
        return run
    if failed:
        run.status, run.error_code, run.error_message = (
            "failed",
            "SUBMIT_FAILED",
            "The runtime could not accept this run. Check execution v2 compatibility.",
        )
        run.completed_at = datetime.now(UTC)
        end_events(db, run)
    else:
        run.status, run.submitted_at = "accepted", datetime.now(UTC)
    await db.commit()
    return run


async def refresh(
    db: AsyncSession,
    client: AgentClient,
    run_id: str,
    applications: dict[str, AgentApplication],
    deadline_seconds: int = 600,
    queued_grace_seconds: float = 180,
) -> AgentRun | None:
    run = await db.get(AgentRun, run_id, populate_existing=True)
    if run is None or run.status in ("succeeded", "failed"):
        await db.commit()
        return run
    if run.status == "queued" and datetime.now(UTC) < run.created_at + timedelta(
        seconds=queued_grace_seconds
    ):
        await db.commit()
        return run
    cursor = run.runtime_cursor
    expired = datetime.now(UTC) >= run.created_at + timedelta(seconds=deadline_seconds)
    await db.commit()
    status = None
    failure = None
    if expired:
        failure = ("TIMEOUT", "The agent took too long.")
    else:
        try:
            status = await client.poll_execution(run_id, cursor)
        except AgentRunNotFound:
            failure = ("AGENT_RUN_LOST", "The agent restarted and lost this run. Start a new run.")
        except (ValueError, AgentClientError):
            return run  # transient; the next refresh retries until the timeout
    run = await db.scalar(
        select(AgentRun)
        .where(AgentRun.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if run is None or run.status in ("succeeded", "failed"):
        await db.commit()
        return run
    run.last_polled_at = datetime.now(UTC)
    if failure:
        run.status, run.error_code, run.error_message = "failed", *failure
    elif status:
        for index, event in enumerate(status.events, start=cursor + 1):
            if index > run.runtime_cursor:
                # Lifecycle is published by the app, after durable validation/finalisation.
                if event.get("type") not in ("RUN_STARTED", "RUN_FINISHED", "RUN_ERROR"):
                    append_event(db, run, event)
                run.runtime_cursor = index
        run.status, run.mlflow_trace_id = status.status, status.trace_id
        if status.status == "failed":
            run.error_code, run.error_message = "MODEL_ERROR", status.error
        elif status.status == "succeeded":
            try:
                async with db.begin_nested():
                    app = applications[run.agent_id]
                    result = app.result_model.model_validate(status.result).model_dump(mode="json")
                    await app.finalize(db, run, result)
                    run.result = result
                    run.materialised_at = datetime.now(UTC)
                    append_event(
                        db,
                        run,
                        event_json(
                            StateSnapshotEvent(
                                type=EventType.STATE_SNAPSHOT,
                                snapshot={"result": result, "provisional": False},
                            )
                        ),
                    )
            except Exception:
                import logging

                logging.getLogger(__name__).exception("Run finalisation failed")
                # Savepoint rollback expires fields changed during finalisation, including the
                # event cursor. Reload explicitly before appending the durable failure event.
                await db.refresh(run)
                run.status, run.error_code, run.error_message = (
                    "failed",
                    "MATERIALISATION_FAILED",
                    "The result could not be validated or saved.",
                )
    if run.status in ("succeeded", "failed"):
        run.completed_at = datetime.now(UTC)
        end_events(db, run)
    await db.commit()
    return run


async def event_batch(db: AsyncSession, run: AgentRun, after: int) -> dict[str, Any]:
    rows = (
        await db.scalars(
            select(RunEvent)
            .where(RunEvent.run_id == run.id, RunEvent.sequence > after)
            .order_by(RunEvent.sequence)
            .limit(500)
        )
    ).all()
    return {
        "events": [{"sequence": row.sequence, "event": row.event} for row in rows],
        "cursor": rows[-1].sequence if rows else after,
        "terminal": run.status in ("succeeded", "failed")
        and (not rows or rows[-1].sequence == run.event_count),
    }
