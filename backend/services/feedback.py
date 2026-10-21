"""Users' feedback on agent output, kept in Lakebase and delivered to the run's MLflow trace.

What is captured (the names are the contract's, section 7):

  field_rating         thumbs up/down on a field the agent wrote, with reasons and a comment
  answer_rating        thumbs up/down on an assistant answer
  suggestion_accepted  true when an enhance_field suggestion is accepted, false when dismissed
  <field path>         an expectation: the value a user corrected an agent-written field to

Each is saved here first, so a request never waits on MLflow, then delivered through the agent's
POST /agent/feedback - straight after the request, and by FeedbackSender for anything that failed.
In Databricks the assessments show on each trace; ``evals/from_feedback.py`` turns them into an
evaluation dataset.
"""

import logging
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.auth.principal import Principal
from backend.contracts.agent_contract_v1 import FeedbackRequest, expectation_name
from backend.domain.enums import FieldSource
from backend.domain.errors import ConflictError, NotFoundError
from backend.domain.models import AgentRun, Document, DocumentField, Feedback, Message, new_id
from backend.services import assistant
from backend.services.agent_client import AgentClient, AgentClientError, AgentRemoteError

logger = logging.getLogger(__name__)

PENDING, SYNCED, SKIPPED, FAILED = "pending", "synced", "skipped", "failed"
MAX_ATTEMPTS = 8
BASE_BACKOFF = timedelta(seconds=30)
MAX_BACKOFF = timedelta(hours=1)
MESSAGE_PREFIX = "message:"


async def record(
    db: AsyncSession,
    *,
    run: AgentRun,
    principal: str,
    kind: str,
    name: str,
    target: str,
    value: Any,
    reasons: Iterable[str] = (),
    comment: str | None = None,
) -> Feedback:
    """One row per user and target. A change bumps the revision and queues it for delivery; the
    new revision replaces the previous one's assessment on the trace."""
    reasons = sorted(set(reasons))
    status = PENDING if run.mlflow_trace_id else SKIPPED
    key = {
        "agent_run_id": run.id,
        "kind": kind,
        "name": name,
        "target": target,
        "principal": principal,
    }
    inserted = await db.scalar(
        insert(Feedback)
        .values(
            id=new_id(),
            document_id=run.document_id,
            trace_id=run.mlflow_trace_id,
            value=value,
            reasons=reasons,
            comment=comment,
            revision=1,
            sync_status=status,
            sync_attempts=0,
            **key,
        )
        .on_conflict_do_nothing(constraint="uq_feedback_target")
        .returning(Feedback.id)
    )
    row = await db.scalar(
        select(Feedback)
        .filter_by(**key)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert row is not None
    if inserted is None and (row.value, row.reasons, row.comment) != (value, reasons, comment):
        row.value, row.reasons, row.comment = value, reasons, comment
        row.revision += 1
        row.updated_at = datetime.now(UTC)
        # If the previous revision never reached the trace, this one replaces what that one would have.
        row.replaces_assessment_id = row.assessment_id or row.replaces_assessment_id
        row.assessment_id = None
        row.sync_status, row.sync_attempts, row.next_attempt_at, row.sync_error = (
            status,
            0,
            None,
            None,
        )
    return row


async def rate_field(
    db: AsyncSession,
    principal: Principal,
    document: Document,
    field_path: str,
    *,
    rating: bool,
    reasons: Iterable[str] = (),
    comment: str | None = None,
) -> Feedback:
    field = await db.get(DocumentField, (document.id, field_path))
    if field is None or field.source != FieldSource.AGENT or field.agent_run_id is None:
        raise ConflictError("Only values the agent wrote can be rated")
    run = await db.get(AgentRun, field.agent_run_id)
    if run is None:
        raise NotFoundError("The run that wrote this value is gone")
    return await record(
        db,
        run=run,
        principal=principal.email,
        kind="feedback",
        name="field_rating",
        target=field_path,
        value=rating,
        reasons=reasons,
        comment=comment,
    )


async def rate_answer(
    db: AsyncSession,
    principal: Principal,
    message_id: int,
    *,
    rating: bool,
    reasons: Iterable[str] = (),
    comment: str | None = None,
) -> tuple[Feedback, Message]:
    message = await db.get(Message, message_id)
    if message is None or message.role != "assistant" or message.agent_run_id is None:
        raise NotFoundError("Answer not found")
    await assistant.require_thread(db, principal, message.thread_id)  # conversations are private
    run = await db.get(AgentRun, message.agent_run_id)
    if run is None:
        raise NotFoundError("The run that wrote this answer is gone")
    row = await record(
        db,
        run=run,
        principal=principal.email,
        kind="feedback",
        name="answer_rating",
        target=f"{MESSAGE_PREFIX}{message.id}",
        value=rating,
        reasons=reasons,
        comment=comment,
    )
    return row, message


async def record_verdict(
    db: AsyncSession, principal: Principal, run: AgentRun, field_path: str, *, accepted: bool
) -> Feedback:
    """The user accepted (true) or dismissed (false) an enhance_field suggestion."""
    return await record(
        db,
        run=run,
        principal=principal.email,
        kind="feedback",
        name="suggestion_accepted",
        target=field_path,
        value=accepted,
    )


async def record_correction(
    db: AsyncSession, principal: Principal, run: AgentRun, field_path: str, value: Any
) -> Feedback:
    """The user changed a value the agent wrote: the new value is ground truth for that run."""
    return await record(
        db,
        run=run,
        principal=principal.email,
        kind="expectation",
        name=expectation_name(field_path),
        target=field_path,
        value=value,
    )


async def my_ratings(
    db: AsyncSession, principal: Principal, document_id: str
) -> dict[tuple[str, str], Feedback]:
    """The principal's ratings on a document, keyed by (agent run id, target)."""
    rows = await db.scalars(
        select(Feedback).where(
            Feedback.document_id == document_id,
            Feedback.principal == principal.email,
            Feedback.name.in_(("field_rating", "answer_rating")),
        )
    )
    return {(row.agent_run_id, row.target): row for row in rows}


# ---- delivery to the trace ----------------------------------------------------------------------


def _request(row: Feedback, run: AgentRun, document_type: str) -> FeedbackRequest:
    assert row.trace_id is not None
    metadata = {
        "app_agent_run_id": run.id,
        "run_kind": run.run_kind,
        "document_id": row.document_id,
        "document_type": document_type,
    }
    if row.target.startswith(MESSAGE_PREFIX):
        metadata["message_id"] = row.target.removeprefix(MESSAGE_PREFIX)
        if run.thread_id:
            metadata["thread_id"] = run.thread_id
    else:
        metadata["field_path"] = row.target
    if row.reasons:
        metadata["reasons"] = ",".join(row.reasons)
    return FeedbackRequest(
        feedback_id=f"{row.id}.{row.revision}",  # the agent stores each revision once
        trace_id=row.trace_id,
        kind="expectation" if row.kind == "expectation" else "feedback",
        name=row.name,
        value=row.value,
        rationale=row.comment,
        user=row.principal,
        metadata=metadata,
        replaces=row.replaces_assessment_id,
    )


async def deliver(db: AsyncSession, client: AgentClient, feedback_id: str) -> None:
    """Send one pending feedback row to the agent. Skips rows another worker is sending."""
    row = await db.scalar(
        select(Feedback)
        .where(Feedback.id == feedback_id, Feedback.sync_status == PENDING)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    if row is None:
        await db.commit()
        return
    run = await db.get(AgentRun, row.agent_run_id)
    document = await db.get(Document, row.document_id)
    if run is None or document is None or row.trace_id is None:
        row.sync_status = SKIPPED
        await db.commit()
        return
    try:
        request = _request(row, run, document.document_type)
    except ValueError as exc:  # it can never be sent as it is
        _retry_later(row, str(exc), permanent=True)
        await db.commit()
        return
    try:
        result = await client.send_feedback(request)
    except AgentRemoteError as exc:
        _retry_later(row, str(exc), permanent=not exc.retryable)
    except AgentClientError as exc:
        _retry_later(row, str(exc))
    else:
        row.sync_status = SYNCED if result.recorded else SKIPPED
        row.assessment_id = result.assessment_id
        row.replaces_assessment_id = None
        row.sync_error = None
    await db.commit()


def _retry_later(row: Feedback, error: str, *, permanent: bool = False) -> None:
    row.sync_attempts += 1
    row.sync_error = error[:1000]
    if permanent or row.sync_attempts >= MAX_ATTEMPTS:
        row.sync_status = FAILED
        logger.warning("Giving up on feedback %s: %s", row.id, error)
        return
    delay = min(MAX_BACKOFF, BASE_BACKOFF * 2 ** (row.sync_attempts - 1))
    row.next_attempt_at = datetime.now(UTC) + delay


async def deliver_due(
    sessions: async_sessionmaker[AsyncSession], client: AgentClient, *, limit: int = 50
) -> int:
    """Send pending feedback whose next attempt is due. Returns how many were tried."""
    async with sessions() as db:
        ids = list(
            await db.scalars(
                select(Feedback.id)
                .where(
                    Feedback.sync_status == PENDING,
                    or_(
                        Feedback.next_attempt_at.is_(None),
                        Feedback.next_attempt_at <= datetime.now(UTC),
                    ),
                )
                .order_by(Feedback.updated_at)
                .limit(limit)
            )
        )
    for feedback_id in ids:
        async with sessions() as db:
            try:
                await deliver(db, client, feedback_id)
            except Exception:
                logger.exception("Delivering feedback %s failed", feedback_id)
    return len(ids)
