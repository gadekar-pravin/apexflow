"""Integration test fixtures for ApexFlow tests.

Provides real asyncpg pool and table cleanup for tests that require AlloyDB.
"""

from __future__ import annotations

import os

import pytest

_ALL_TABLES = [
    "scanned_runs",
    "chat_messages",
    "chat_sessions",
    "document_chunks",
    "documents",
    "job_runs",
    "notifications",
    "memories",
    "jobs",
    "sessions",
    "user_preferences",
    "system_state",
    "security_logs",
]


@pytest.fixture(scope="session")
async def db_pool():  # type: ignore[no-untyped-def]
    """Real asyncpg pool for integration tests. Skips if DB is unreachable."""
    db_url = os.environ.get("DATABASE_TEST_URL")
    if not db_url:
        host = os.environ.get("DB_HOST", "localhost")
        port = os.environ.get("DB_PORT", "5432")
        user = os.environ.get("DB_USER", "apexflow")
        password = os.environ.get("DB_PASSWORD", "apexflow")
        db_name = os.environ.get("DB_NAME", "apexflow")
        db_url = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
    try:
        import asyncpg

        async def _init_conn(conn):  # type: ignore[no-untyped-def]
            try:
                from pgvector.asyncpg import register_vector

                await register_vector(conn)
            except Exception:
                pass

        pool = await asyncpg.create_pool(db_url, min_size=1, max_size=3, init=_init_conn)
    except Exception as exc:
        pytest.skip(f"Test database not available: {exc}")
        return  # unreachable but satisfies type checker

    yield pool
    await pool.close()


@pytest.fixture
async def clean_tables(db_pool):  # type: ignore[no-untyped-def]
    """Truncate all tables before and after each test."""
    tables = ", ".join(_ALL_TABLES)
    async with db_pool.acquire() as conn:
        await conn.execute(f"TRUNCATE {tables} CASCADE")
    yield
    async with db_pool.acquire() as conn:
        await conn.execute(f"TRUNCATE {tables} CASCADE")
