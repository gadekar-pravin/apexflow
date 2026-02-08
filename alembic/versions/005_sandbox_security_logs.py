"""Add details JSONB column to security_logs table.

Revision ID: 005
Revises: 004
Create Date: 2026-02-08

"""

from collections.abc import Sequence

from alembic import op

revision: str = "005"
down_revision: str = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE security_logs ADD COLUMN IF NOT EXISTS details JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE security_logs DROP COLUMN IF EXISTS details")
