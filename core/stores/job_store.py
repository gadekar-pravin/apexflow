"""Job store -- CRUD for the ``jobs`` table."""

from __future__ import annotations

import json
import logging
from typing import Any

from core.database import get_pool

logger = logging.getLogger(__name__)


class JobStore:
    """Stateless data-access object for scheduled jobs."""

    async def load_all(self, user_id: str) -> list[dict[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM jobs WHERE user_id = $1 ORDER BY created_at",
                user_id,
            )
        return [dict(r) for r in rows]

    async def get(self, user_id: str, job_id: str) -> dict[str, Any] | None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM jobs WHERE id = $1 AND user_id = $2",
                job_id,
                user_id,
            )
        return dict(row) if row else None

    async def create(
        self,
        user_id: str,
        job_id: str,
        *,
        name: str,
        cron_expression: str,
        query: str,
        agent_type: str = "PlannerAgent",
        skill_id: str | None = None,
        enabled: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO jobs (id, user_id, name, cron_expression, agent_type,
                                  query, skill_id, enabled, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
                RETURNING *
                """,
                job_id,
                user_id,
                name,
                cron_expression,
                agent_type,
                query,
                skill_id,
                enabled,
                json.dumps(metadata or {}),
            )
        return dict(row) if row else {}

    _UPDATABLE_COLUMNS = frozenset(
        {
            "name",
            "cron_expression",
            "query",
            "agent_type",
            "skill_id",
            "enabled",
            "last_run",
            "next_run",
            "last_output",
            "metadata",
        }
    )

    async def update(self, user_id: str, job_id: str, **fields: Any) -> None:
        if not fields:
            return
        invalid = set(fields) - self._UPDATABLE_COLUMNS
        if invalid:
            raise ValueError(f"Invalid columns for update: {invalid}")
        pool = await get_pool()
        # Build SET clause dynamically (column names validated against allowlist)
        set_parts: list[str] = []
        values: list[Any] = []
        idx = 3  # $1=job_id, $2=user_id
        for col, val in fields.items():
            if col == "metadata" and isinstance(val, dict):
                set_parts.append(f"{col} = ${idx}::jsonb")
                values.append(json.dumps(val))
            else:
                set_parts.append(f"{col} = ${idx}")
                values.append(val)
            idx += 1
        sql = f"UPDATE jobs SET {', '.join(set_parts)} WHERE id = $1 AND user_id = $2"
        async with pool.acquire() as conn:
            await conn.execute(sql, job_id, user_id, *values)

    async def delete(self, user_id: str, job_id: str) -> bool:
        pool = await get_pool()
        async with pool.acquire() as conn:
            tag = await conn.execute(
                "DELETE FROM jobs WHERE id = $1 AND user_id = $2",
                job_id,
                user_id,
            )
        return tag == "DELETE 1"
