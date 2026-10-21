"""Baseline schema: documents and their fields, versions, audit log and access; agent runs;
assistant threads and messages; idempotency keys; role assignments; notifications.

Revision ID: 0001
Revises:
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        schema="app",
    )
    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("principal", sa.String(length=320), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", "principal", name=op.f("pk_idempotency_keys")),
        schema="app",
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("link", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        schema="app",
    )
    op.create_index(
        "ix_notifications_recipient_read_at",
        "notifications",
        ["recipient", "read_at"],
        unique=False,
        schema="app",
    )
    op.create_table(
        "role_assignments",
        sa.Column("principal", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("granted_by", sa.String(length=320), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("principal", "role", name=op.f("pk_role_assignments")),
        schema="app",
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("field_path", sa.String(length=200), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("value_before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("value_after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("actor", sa.String(length=320), nullable=False),
        sa.Column("agent_run_id", sa.String(length=36), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["app.documents.id"],
            name=op.f("fk_audit_log_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
        schema="app",
    )
    op.create_index(
        "ix_audit_log_document_id_id",
        "audit_log",
        ["document_id", "id"],
        unique=False,
        schema="app",
    )
    op.create_table(
        "document_access",
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("principal", sa.String(length=320), nullable=False),
        sa.Column("access", sa.String(length=16), nullable=False),
        sa.Column("granted_by", sa.String(length=320), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["app.documents.id"],
            name=op.f("fk_document_access_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("document_id", "principal", name=op.f("pk_document_access")),
        schema="app",
    )
    op.create_index(
        op.f("ix_document_access_principal"),
        "document_access",
        ["principal"],
        unique=False,
        schema="app",
    )
    op.create_table(
        "document_fields",
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("field_path", sa.String(length=200), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=True),
        sa.Column("confidence_reason", sa.Text(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("agent_run_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=320), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["app.documents.id"],
            name=op.f("fk_document_fields_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("document_id", "field_path", name=op.f("pk_document_fields")),
        schema="app",
    )
    op.create_table(
        "document_versions",
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("agent_run_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["app.documents.id"],
            name=op.f("fk_document_versions_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("document_id", "version", name=op.f("pk_document_versions")),
        schema="app",
    )
    op.create_table(
        "threads",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("owner", sa.String(length=320), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["app.documents.id"],
            name=op.f("fk_threads_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_threads")),
        schema="app",
    )
    op.create_index(
        op.f("ix_threads_document_id"), "threads", ["document_id"], unique=False, schema="app"
    )
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=True),
        sa.Column("run_kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("triggered_by", sa.String(length=320), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("step_history", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("mlflow_trace_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("materialised_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["app.documents.id"],
            name=op.f("fk_agent_runs_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["app.threads.id"],
            name=op.f("fk_agent_runs_thread_id_threads"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_runs")),
        schema="app",
    )
    op.create_index(
        op.f("ix_agent_runs_document_id"), "agent_runs", ["document_id"], unique=False, schema="app"
    )
    op.create_index(
        "ix_agent_runs_status_last_polled_at",
        "agent_runs",
        ["status", "last_polled_at"],
        unique=False,
        schema="app",
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("agent_run_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["app.threads.id"],
            name=op.f("fk_messages_thread_id_threads"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
        schema="app",
    )
    op.create_index(
        "ix_messages_thread_id_id", "messages", ["thread_id", "id"], unique=False, schema="app"
    )


def downgrade() -> None:
    op.drop_index("ix_messages_thread_id_id", table_name="messages", schema="app")
    op.drop_table("messages", schema="app")
    op.drop_index("ix_agent_runs_status_last_polled_at", table_name="agent_runs", schema="app")
    op.drop_index(op.f("ix_agent_runs_document_id"), table_name="agent_runs", schema="app")
    op.drop_table("agent_runs", schema="app")
    op.drop_index(op.f("ix_threads_document_id"), table_name="threads", schema="app")
    op.drop_table("threads", schema="app")
    op.drop_table("document_versions", schema="app")
    op.drop_table("document_fields", schema="app")
    op.drop_index(op.f("ix_document_access_principal"), table_name="document_access", schema="app")
    op.drop_table("document_access", schema="app")
    op.drop_index("ix_audit_log_document_id_id", table_name="audit_log", schema="app")
    op.drop_table("audit_log", schema="app")
    op.drop_table("role_assignments", schema="app")
    op.drop_index("ix_notifications_recipient_read_at", table_name="notifications", schema="app")
    op.drop_table("notifications", schema="app")
    op.drop_table("idempotency_keys", schema="app")
    op.drop_table("documents", schema="app")
