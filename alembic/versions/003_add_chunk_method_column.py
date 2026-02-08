"""Add chunk_method column to documents table.

Revision ID: 003
Revises: 002
Create Date: 2026-02-08

"""

from collections.abc import Sequence

from alembic import op

revision: str = "003"
down_revision: str = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS chunk_method TEXT NOT NULL DEFAULT 'rule_based'"
        " CHECK (chunk_method IN ('rule_based', 'semantic'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS chunk_method")
