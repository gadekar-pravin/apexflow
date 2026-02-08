"""Add RAG versioning columns to documents table.

Revision ID: 002
Revises: 001
Create Date: 2026-02-08

"""

from collections.abc import Sequence

from alembic import op

revision: str = "002"
down_revision: str = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS content TEXT")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_model TEXT")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_dim INTEGER")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS ingestion_version INTEGER DEFAULT 1")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()")


def downgrade() -> None:
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS ingestion_version")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS embedding_dim")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS embedding_model")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS content")
