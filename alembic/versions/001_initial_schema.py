"""Initial schema — 13 tables from scripts/init-db.sql.

Revision ID: 001
Revises:
Create Date: 2025-02-07

"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INIT_SQL = Path(__file__).resolve().parent.parent.parent / "scripts" / "init-db.sql"


def upgrade() -> None:
    sql = _INIT_SQL.read_text()
    op.execute(sql)


def downgrade() -> None:
    # Reverse order of creation — drop all tables
    op.execute("DROP TABLE IF EXISTS security_logs CASCADE")
    op.execute("DROP TABLE IF EXISTS scanned_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS system_state CASCADE")
    op.execute("DROP TABLE IF EXISTS user_preferences CASCADE")
    op.execute("DROP TABLE IF EXISTS chat_messages CASCADE")
    op.execute("DROP TABLE IF EXISTS chat_sessions CASCADE")
    op.execute("DROP TABLE IF EXISTS document_chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS documents CASCADE")
    op.execute("DROP TABLE IF EXISTS memories CASCADE")
    op.execute("DROP TABLE IF EXISTS notifications CASCADE")
    op.execute("DROP TABLE IF EXISTS job_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS jobs CASCADE")
    op.execute("DROP TABLE IF EXISTS sessions CASCADE")
    op.execute("DROP EXTENSION IF EXISTS alloydb_scann")
    op.execute("DROP EXTENSION IF EXISTS vector")
