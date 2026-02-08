"""Job run store -- dedup and tracking for ``job_runs`` table."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from core.database import get_pool

logger = logging.getLogger(__name__)


class JobRunStore:
    """Stateless data-access object for job execution dedup."""

    async def try_claim(
        self,
        user_id: str,
        job_id: str,
        scheduled_for: datetime,
    ) -> bool:
        """Attempt to claim a job run slot.

        Returns True if the row was inserted (this worker wins),
        False if another worker already claimed it.
        """
        pool = await get_pool()
        async with pool.acquire() as conn:
            tag = await conn.execute(
                """
                INSERT INTO job_runs (job_id, user_id, scheduled_for)
                VALUES ($1, $2, $3)
                ON CONFLICT (job_id, scheduled_for) DO NOTHING
                """,
                job_id,
                user_id,
                scheduled_for,
            )
        # tag is "INSERT 0 1" on success, "INSERT 0 0" on conflict
        return tag == "INSERT 0 1"

    async def complete(
        self,
        user_id: str,
        job_id: str,
        scheduled_for: datetime,
        status: str,
        output: str | None = None,
        error: str | None = None,
    ) -> None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE job_runs
                SET status = $4, output = $5, error = $6, completed_at = NOW()
                WHERE job_id = $1 AND user_id = $2 AND scheduled_for = $3
                """,
                job_id,
                user_id,
                scheduled_for,
                status,
                output,
                error,
            )

    async def recent(
        self,
        user_id: str,
        job_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM job_runs
                WHERE job_id = $1 AND user_id = $2
                ORDER BY scheduled_for DESC
                LIMIT $3
                """,
                job_id,
                user_id,
                limit,
            )
        return [dict(r) for r in rows]
