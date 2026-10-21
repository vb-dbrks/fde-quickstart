"""Feedback outbox: users' ratings, verdicts and corrections, delivered to the run's MLflow trace.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("agent_run_id", sa.String(length=36), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("target", sa.String(length=200), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("principal", sa.String(length=320), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
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
        sa.Column("sync_status", sa.String(length=16), nullable=False),
        sa.Column("sync_attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_error", sa.Text(), nullable=True),
        sa.Column("assessment_id", sa.String(length=64), nullable=True),
        sa.Column("replaces_assessment_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["app.agent_runs.id"],
            name=op.f("fk_feedback_agent_run_id_agent_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["app.documents.id"],
            name=op.f("fk_feedback_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feedback")),
        sa.UniqueConstraint(
            "agent_run_id", "kind", "name", "target", "principal", name="uq_feedback_target"
        ),
        schema="app",
    )
    op.create_index(
        op.f("ix_feedback_document_id"), "feedback", ["document_id"], unique=False, schema="app"
    )
    op.create_index(
        "ix_feedback_sync_status_next_attempt_at",
        "feedback",
        ["sync_status", "next_attempt_at"],
        unique=False,
        schema="app",
    )


def downgrade() -> None:
    op.drop_index("ix_feedback_sync_status_next_attempt_at", table_name="feedback", schema="app")
    op.drop_index(op.f("ix_feedback_document_id"), table_name="feedback", schema="app")
    op.drop_table("feedback", schema="app")
