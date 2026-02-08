"""Add embedding_model column to memories table.

Revision ID: 004
Revises: 003
Create Date: 2026-02-08

"""

from collections.abc import Sequence

from alembic import op

revision: str = "004"
down_revision: str = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE memories ADD COLUMN IF NOT EXISTS embedding_model TEXT DEFAULT 'text-embedding-004'")


def downgrade() -> None:
    op.execute("ALTER TABLE memories DROP COLUMN IF EXISTS embedding_model")
