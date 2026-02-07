"""Async database connection pool with environment auto-detection."""

from __future__ import annotations

import logging
import os

import asyncpg

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


class DatabaseConfig:
    """Builds connection strings based on detected environment."""

    @staticmethod
    def get_connection_string() -> str:
        # Priority 1: Explicit override (any environment)
        if url := os.environ.get("DATABASE_URL"):
            return url

        # Priority 2: Cloud Run -> managed AlloyDB
        if os.environ.get("K_SERVICE"):
            host = os.environ.get("ALLOYDB_HOST")
            db = os.environ.get("ALLOYDB_DB", "apexflow")
            user = os.environ.get("ALLOYDB_USER", "apexflow")
            password = os.environ.get("ALLOYDB_PASSWORD", "")
            return f"postgresql://{user}:{password}@{host}/{db}"

        # Priority 3: Local dev -> GCE VM (or localhost fallback)
        sslmode = os.environ.get("DB_SSLMODE", "disable")
        return (
            f"postgresql://{os.environ.get('DB_USER', 'apexflow')}:"
            f"{os.environ.get('DB_PASSWORD', 'apexflow')}@"
            f"{os.environ.get('DB_HOST', 'localhost')}:"
            f"{os.environ.get('DB_PORT', '5432')}/"
            f"{os.environ.get('DB_NAME', 'apexflow')}?sslmode={sslmode}"
        )


async def get_pool() -> asyncpg.Pool:
    """Return the singleton connection pool, creating it if necessary."""
    global _pool  # noqa: PLW0603
    if _pool is None:
        dsn = DatabaseConfig.get_connection_string()
        logger.info("Creating database pool (host hidden for security)")
        _pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=1,
            max_size=int(os.environ.get("DB_POOL_MAX", "5")),
            command_timeout=30,
        )
    return _pool


async def close_pool() -> None:
    """Gracefully close the connection pool."""
    global _pool  # noqa: PLW0603
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")


async def check_db_connection() -> bool:
    """Health check: returns True if the database is reachable."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception:
        logger.exception("Database health check failed")
        return False
