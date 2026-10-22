"""ORM models: the app's system of record in Lakebase.

Documents hold their content as one row per field (``document_fields``), keyed by the field paths in
contracts/field-catalog.yaml, with the provenance of agent-written values. ``agent_runs`` mirrors every
agent invocation, including the exact request and response, so any run can be replayed.

After changing a model, add a migration: `make migration MSG="describe the change"`.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.elements import ColumnElement

from backend.db.base import Base

EMAIL_LENGTH = 320
ID_LENGTH = 36


def new_id() -> str:
    return str(uuid.uuid4())


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_id)
    document_type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    current_version: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(EMAIL_LENGTH))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentField(Base):
    """The current value of one field, and where it came from."""

    __tablename__ = "document_fields"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    field_path: Mapped[str] = mapped_column(String(200), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    value: Mapped[Any] = mapped_column(JSONB, nullable=True)
    source: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[str | None] = mapped_column(String(16))
    confidence_reason: Mapped[str | None] = mapped_column(Text)
    reasoning: Mapped[str | None] = mapped_column(Text)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    agent_run_id: Mapped[str | None] = mapped_column(String(ID_LENGTH))
    updated_by: Mapped[str] = mapped_column(String(EMAIL_LENGTH))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DocumentVersion(Base):
    """A snapshot of every field, taken each time an agent run is materialised."""

    __tablename__ = "document_versions"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    agent_run_id: Mapped[str | None] = mapped_column(String(ID_LENGTH))
    created_by: Mapped[str] = mapped_column(String(EMAIL_LENGTH))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """Append-only history of changes to documents, fields and access."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_document_id_id", "document_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    field_path: Mapped[str | None] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(32))
    value_before: Mapped[Any] = mapped_column(JSONB, nullable=True)
    value_after: Mapped[Any] = mapped_column(JSONB, nullable=True)
    actor: Mapped[str] = mapped_column(String(EMAIL_LENGTH))
    agent_run_id: Mapped[str | None] = mapped_column(String(ID_LENGTH))
    trace_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentAccess(Base):
    """Who can see or change a document. The creator is the first owner."""

    __tablename__ = "document_access"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    principal: Mapped[str] = mapped_column(String(EMAIL_LENGTH), primary_key=True, index=True)
    access: Mapped[str] = mapped_column(String(16))
    granted_by: Mapped[str] = mapped_column(String(EMAIL_LENGTH))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentRun(Base):
    """One agent invocation. The id doubles as the agent contract's ``app_agent_run_id``."""

    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_status_last_polled_at", "status", "last_polled_at"),)

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_id)
    document_binding: Mapped["DocumentRun | None"] = relationship(
        cascade="all, delete-orphan", lazy="selectin", uselist=False
    )

    @hybrid_property
    def document_id(self) -> str:
        """Compatibility accessor; generic records have no document association."""
        return self.document_binding.document_id if self.document_binding else ""

    @document_id.inplace.setter
    def _set_document_id(self, value: str) -> None:
        self.document_binding = DocumentRun(document_id=value) if value else None

    @document_id.inplace.expression
    @classmethod
    def _document_id_expression(cls) -> ColumnElement[str]:
        return select(DocumentRun.document_id).where(DocumentRun.run_id == cls.id).scalar_subquery()

    thread_id: Mapped[str | None] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"))
    run_kind: Mapped[str] = mapped_column(String(100))
    agent_id: Mapped[str] = mapped_column(
        String(100), default="documents", server_default="documents"
    )
    contract_version: Mapped[str] = mapped_column(String(8), default="v1", server_default="v1")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    runtime_cursor: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    event_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    review_required: Mapped[bool] = mapped_column(default=False, server_default="false")
    status: Mapped[str] = mapped_column(String(16))
    triggered_by: Mapped[str] = mapped_column(String(EMAIL_LENGTH))
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    step_history: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    mlflow_trace_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set once the output has been written to the document; guards against double materialisation.
    materialised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Thread(Base):
    """An assistant conversation about a document. Private to its owner."""

    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_id)
    document_binding: Mapped["DocumentThread | None"] = relationship(
        cascade="all, delete-orphan", lazy="selectin", uselist=False
    )

    @hybrid_property
    def document_id(self) -> str:
        """Compatibility accessor; generic records have no document association."""
        return self.document_binding.document_id if self.document_binding else ""

    @document_id.inplace.setter
    def _set_document_id(self, value: str) -> None:
        self.document_binding = DocumentThread(document_id=value) if value else None

    @document_id.inplace.expression
    @classmethod
    def _document_id_expression(cls) -> ColumnElement[str]:
        return (
            select(DocumentThread.document_id)
            .where(DocumentThread.thread_id == cls.id)
            .scalar_subquery()
        )

    agent_id: Mapped[str] = mapped_column(
        String(100), default="documents.assistant_turn", server_default="documents.assistant_turn"
    )
    owner: Mapped[str] = mapped_column(String(EMAIL_LENGTH))
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_thread_id_id", "thread_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    agent_run_id: Mapped[str | None] = mapped_column(String(ID_LENGTH))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Feedback(Base):
    """A user's feedback on agent output: a rating, an accept/dismiss verdict, or a correction.

    Kept here first, then stored on the run's MLflow trace through the agent (an outbox: the
    ``sync_*`` columns track delivery). One row per user and target; changing your mind updates the
    row and bumps ``revision``, and the new revision replaces the old assessment on the trace.
    """

    __tablename__ = "feedback"
    __table_args__ = (
        UniqueConstraint(
            "agent_run_id", "kind", "name", "target", "principal", name="uq_feedback_target"
        ),
        Index("ix_feedback_sync_status_next_attempt_at", "sync_status", "next_attempt_at"),
    )

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_id)
    document_binding: Mapped["DocumentFeedback | None"] = relationship(
        cascade="all, delete-orphan", lazy="selectin", uselist=False
    )

    @hybrid_property
    def document_id(self) -> str:
        """Compatibility accessor; generic records have no document association."""
        return self.document_binding.document_id if self.document_binding else ""

    @document_id.inplace.setter
    def _set_document_id(self, value: str) -> None:
        self.document_binding = DocumentFeedback(document_id=value) if value else None

    @document_id.inplace.expression
    @classmethod
    def _document_id_expression(cls) -> ColumnElement[str]:
        return (
            select(DocumentFeedback.document_id)
            .where(DocumentFeedback.feedback_id == cls.id)
            .scalar_subquery()
        )

    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    # Copied from the run; null when the run was not traced (then there is nothing to deliver).
    trace_id: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))  # feedback | expectation
    name: Mapped[str] = mapped_column(String(200))  # field_rating, ... or the field path
    target: Mapped[str] = mapped_column(String(200))  # the field path, or message:<id>
    value: Mapped[Any] = mapped_column(JSONB)
    reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)
    comment: Mapped[str | None] = mapped_column(Text)
    principal: Mapped[str] = mapped_column(String(EMAIL_LENGTH))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Delivery to the trace: pending -> synced, or skipped (tracing off) / failed (gave up).
    sync_status: Mapped[str] = mapped_column(String(16), default="pending")
    sync_attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_error: Mapped[str | None] = mapped_column(Text)
    assessment_id: Mapped[str | None] = mapped_column(String(64))
    # The assessment this revision replaces on the trace (the previous revision's).
    replaces_assessment_id: Mapped[str | None] = mapped_column(String(64))


class IdempotencyKey(Base):
    """A mutating request sent with an ``Idempotency-Key`` header, and its stored response.

    ``status_code`` is null while the request is still running (the key is claimed but unanswered).
    """

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    principal: Mapped[str] = mapped_column(String(EMAIL_LENGTH), primary_key=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(500))
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[Any] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RoleAssignment(Base):
    """A role granted to a user. Roles and their permissions are defined in backend.auth.roles."""

    __tablename__ = "role_assignments"

    principal: Mapped[str] = mapped_column(String(EMAIL_LENGTH), primary_key=True)
    role: Mapped[str] = mapped_column(String(32), primary_key=True)
    granted_by: Mapped[str] = mapped_column(String(EMAIL_LENGTH))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    """An in-app notification, shown in the bell menu until read."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_recipient_read_at", "recipient", "read_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient: Mapped[str] = mapped_column(String(EMAIL_LENGTH))
    kind: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentRun(Base):
    __tablename__ = "document_runs"
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )


class DocumentThread(Base):
    __tablename__ = "document_threads"
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("threads.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )


class DocumentFeedback(Base):
    __tablename__ = "document_feedback"
    feedback_id: Mapped[str] = mapped_column(
        ForeignKey("feedback.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )


class RunEvent(Base):
    __tablename__ = "run_events"
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), primary_key=True
    )
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    event: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ToolOutcome(Base):
    __tablename__ = "tool_outcomes"
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), primary_key=True
    )
    tool_call_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)


class GenerationArtifact(Base):
    __tablename__ = "generation_artifacts"
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(16), default="pending")
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)


class FieldProposal(Base):
    __tablename__ = "field_proposals"
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), primary_key=True
    )
    field_path: Mapped[str] = mapped_column(String(200), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    base_revision: Mapped[int] = mapped_column(Integer)
    before: Mapped[Any] = mapped_column(JSONB, nullable=True)
    output: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    accepted_value: Mapped[Any] = mapped_column(JSONB, nullable=True)
