"""ORM models: the app's system of record in Lakebase.

Documents hold their content as one row per field (``document_fields``), keyed by the field paths in
contracts/field-catalog.yaml, with the provenance of agent-written values. ``agent_runs`` mirrors every
agent invocation, including the exact request and response, so any run can be replayed.

After changing a model, add a migration: `make migration MSG="describe the change"`.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

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
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    thread_id: Mapped[str | None] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"))
    run_kind: Mapped[str] = mapped_column(String(32))
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
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
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
