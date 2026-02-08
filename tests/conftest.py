"""Shared pytest fixtures for ApexFlow tests."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helper: canonical mock pool (extracted from test_stores.py pattern)
# ---------------------------------------------------------------------------


def mock_pool(
    fetchrow: Any = None,
    fetch: Any = None,
    fetchval: Any = None,
    execute: Any = None,
    executemany: Any = None,
) -> AsyncMock:
    """Create a mock asyncpg pool with a mock connection."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow)
    conn.fetch = AsyncMock(return_value=fetch or [])
    conn.fetchval = AsyncMock(return_value=fetchval)
    conn.execute = AsyncMock(return_value=execute or "UPDATE 1")
    conn.executemany = AsyncMock(return_value=executemany)

    # transaction context manager
    txn = AsyncMock()
    txn.__aenter__ = AsyncMock(return_value=txn)
    txn.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=txn)

    pool = AsyncMock()
    acq = AsyncMock()
    acq.__aenter__ = AsyncMock(return_value=conn)
    acq.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=acq)

    return pool


# ---------------------------------------------------------------------------
# Fixtures: real DB (integration tests)
# ---------------------------------------------------------------------------

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
    db_url = os.environ.get(
        "DATABASE_TEST_URL",
        "postgresql://apexflow:apexflow@localhost:5432/apexflow",
    )
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


@pytest.fixture
def test_user_id() -> str:
    return "test-user-001"
