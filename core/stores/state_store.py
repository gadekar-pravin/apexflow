"""State store -- user-scoped key-value pairs in ``system_state``."""

from __future__ import annotations

import json
import logging
from typing import Any

from core.database import get_pool

logger = logging.getLogger(__name__)


class StateStore:
    """Stateless data-access object for the system_state table."""

    async def get(self, user_id: str, key: str) -> dict[str, Any] | None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval(
                "SELECT value FROM system_state WHERE user_id = $1 AND key = $2",
                user_id,
                key,
            )
        if val is None:
            return None
        result: dict[str, Any] = json.loads(val) if isinstance(val, str) else val
        return result

    async def set(self, user_id: str, key: str, value: dict[str, Any]) -> None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO system_state (user_id, key, value, updated_at)
                VALUES ($1, $2, $3::jsonb, NOW())
                ON CONFLICT (user_id, key)
                DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
                """,
                user_id,
                key,
                json.dumps(value, default=str),
            )

    async def delete(self, user_id: str, key: str) -> bool:
        pool = await get_pool()
        async with pool.acquire() as conn:
            tag = await conn.execute(
                "DELETE FROM system_state WHERE user_id = $1 AND key = $2",
                user_id,
                key,
            )
        return tag == "DELETE 1"
