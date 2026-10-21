"""Idempotency keys are claimed before the request runs: status_code is null until it answers.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "idempotency_keys", "status_code", existing_type=sa.Integer(), nullable=True, schema="app"
    )


def downgrade() -> None:
    op.execute("DELETE FROM app.idempotency_keys WHERE status_code IS NULL")
    op.alter_column(
        "idempotency_keys", "status_code", existing_type=sa.Integer(), nullable=False, schema="app"
    )
