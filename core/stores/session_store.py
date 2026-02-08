"""Session store -- CRUD + metrics queries for the ``sessions`` table."""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

from core.database import get_pool

logger = logging.getLogger(__name__)


class SessionStore:
    """Stateless data-access object for the sessions table."""

    # -- create / read --------------------------------------------------------

    async def create(
        self,
        user_id: str,
        session_id: str,
        query: str,
        *,
        agent_type: str | None = None,
        model_used: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO sessions (id, user_id, query, agent_type, model_used, metadata)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                RETURNING *
                """,
                session_id,
                user_id,
                query,
                agent_type,
                model_used,
                json.dumps(metadata or {}),
            )
        return dict(row) if row else {}

    async def get(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM sessions WHERE id = $1 AND user_id = $2",
                session_id,
                user_id,
            )
        return dict(row) if row else None

    async def exists(self, user_id: str, session_id: str) -> bool:
        pool = await get_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval(
                "SELECT 1 FROM sessions WHERE id = $1 AND user_id = $2",
                session_id,
                user_id,
            )
        return val is not None

    async def list_sessions(
        self,
        user_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if status:
                rows = await conn.fetch(
                    """
                    SELECT id, query, status, agent_type, cost, model_used,
                           created_at, completed_at
                    FROM sessions
                    WHERE user_id = $1 AND status = $2
                    ORDER BY created_at DESC
                    LIMIT $3 OFFSET $4
                    """,
                    user_id,
                    status,
                    limit,
                    offset,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, query, status, agent_type, cost, model_used,
                           created_at, completed_at
                    FROM sessions
                    WHERE user_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2 OFFSET $3
                    """,
                    user_id,
                    limit,
                    offset,
                )
        return [dict(r) for r in rows]

    async def list_unscanned(self, user_id: str) -> list[dict[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, query, status, graph_data, node_outputs,
                       created_at, completed_at
                FROM sessions
                WHERE user_id = $1 AND NOT remme_scanned
                  AND status IN ('completed', 'failed')
                ORDER BY created_at
                """,
                user_id,
            )
        return [dict(r) for r in rows]

    # -- partial updates ------------------------------------------------------

    async def update_status(
        self,
        user_id: str,
        session_id: str,
        status: str,
        *,
        error: str | None = None,
    ) -> None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if status in ("completed", "failed", "cancelled"):
                await conn.execute(
                    """
                    UPDATE sessions
                    SET status = $3,
                        error = COALESCE($4, error),
                        completed_at = COALESCE(completed_at, NOW())
                    WHERE id = $1 AND user_id = $2
                    """,
                    session_id,
                    user_id,
                    status,
                    error,
                )
            else:
                await conn.execute(
                    """
                    UPDATE sessions
                    SET status = $3, error = COALESCE($4, error)
                    WHERE id = $1 AND user_id = $2
                    """,
                    session_id,
                    user_id,
                    status,
                    error,
                )

    async def update_graph(
        self,
        user_id: str,
        session_id: str,
        graph_data: dict[str, Any],
        node_outputs: dict[str, Any] | None = None,
    ) -> None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE sessions
                SET graph_data = $3::jsonb,
                    node_outputs = COALESCE($4::jsonb, node_outputs)
                WHERE id = $1 AND user_id = $2
                """,
                session_id,
                user_id,
                json.dumps(graph_data, default=str),
                json.dumps(node_outputs, default=str) if node_outputs else None,
            )

    async def update_cost(
        self,
        user_id: str,
        session_id: str,
        delta: float,
    ) -> None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE sessions
                SET cost = cost + $3
                WHERE id = $1 AND user_id = $2
                """,
                session_id,
                user_id,
                Decimal(str(delta)),
            )

    # -- delete / scan --------------------------------------------------------

    async def delete(self, user_id: str, session_id: str) -> bool:
        pool = await get_pool()
        async with pool.acquire() as conn:
            tag = await conn.execute(
                "DELETE FROM sessions WHERE id = $1 AND user_id = $2",
                session_id,
                user_id,
            )
        return tag == "DELETE 1"

    async def mark_scanned(self, user_id: str, session_id: str) -> None:
        """Atomically mark a session as scanned and record the run."""
        pool = await get_pool()
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute(
                """
                    UPDATE sessions SET remme_scanned = TRUE
                    WHERE id = $1 AND user_id = $2
                    """,
                session_id,
                user_id,
            )
            await conn.execute(
                """
                    INSERT INTO scanned_runs (run_id, user_id)
                    VALUES ($1, $2)
                    ON CONFLICT (run_id) DO NOTHING
                    """,
                session_id,
                user_id,
            )

    # -- metrics (SQL aggregation) --------------------------------------------

    async def get_dashboard_stats(self, user_id: str, days: int = 30) -> dict[str, Any]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total_runs,
                    COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                    COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled,
                    COUNT(*) FILTER (WHERE status = 'running') AS running,
                    COALESCE(SUM(cost), 0) AS total_cost,
                    COALESCE(AVG(cost), 0) AS avg_cost
                FROM sessions
                WHERE user_id = $1
                  AND created_at >= NOW() - ($2 || ' days')::INTERVAL
                """,
                user_id,
                str(days),
            )
        if not row:
            return {}
        result = dict(row)
        # Convert Decimal to float for JSON serialization
        for k, v in result.items():
            if isinstance(v, Decimal):
                result[k] = float(v)
        return result

    async def get_daily_stats(self, user_id: str, days: int = 30) -> list[dict[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    DATE(created_at) AS date,
                    COUNT(*) AS runs,
                    COALESCE(SUM(cost), 0) AS cost,
                    COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                    COUNT(*) FILTER (WHERE status = 'failed') AS failed
                FROM sessions
                WHERE user_id = $1
                  AND created_at >= NOW() - ($2 || ' days')::INTERVAL
                GROUP BY DATE(created_at)
                ORDER BY DATE(created_at) DESC
                """,
                user_id,
                str(days),
            )
        result = []
        for r in rows:
            d = dict(r)
            for k, v in d.items():
                if isinstance(v, Decimal):
                    d[k] = float(v)
            result.append(d)
        return result
