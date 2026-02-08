"""Preferences store -- JSONB access on the ``user_preferences`` table."""

from __future__ import annotations

import json
import logging
from typing import Any

from core.database import get_pool

logger = logging.getLogger(__name__)

# Maps logical hub names to their DB column names.
# Only these are valid — prevents SQL injection via hub_name.
_HUB_COLUMNS: dict[str, str] = {
    "preferences": "preferences",
    "operating_context": "operating_ctx",
    "soft_identity": "soft_identity",
    "evidence": "evidence_log",
    "staging": "staging_queue",
}


class PreferencesStore:
    """Stateless data-access object for the user_preferences table."""

    @staticmethod
    def _col(hub_name: str) -> str:
        """Resolve hub name to DB column. Raises ValueError for unknown hubs."""
        col = _HUB_COLUMNS.get(hub_name)
        if col is None:
            raise ValueError(f"Unknown hub name: {hub_name!r} (valid: {sorted(_HUB_COLUMNS)})")
        return col

    async def _ensure_row(self, user_id: str) -> None:
        """Create the user_preferences row if it doesn't exist yet."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO user_preferences (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
                user_id,
            )

    async def get_hub_data(self, user_id: str, hub_name: str) -> dict[str, Any]:
        """Read a single JSONB column for the user. Returns {} if no row."""
        col = self._col(hub_name)
        pool = await get_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval(
                f"SELECT {col} FROM user_preferences WHERE user_id = $1",  # noqa: S608
                user_id,
            )
        if val is None:
            return {}
        result: dict[str, Any] = json.loads(val) if isinstance(val, str) else val
        return result

    async def save_hub_data(
        self,
        user_id: str,
        hub_name: str,
        data: dict[str, Any],
        expected_updated_at: Any = None,
    ) -> bool:
        """Full overwrite of a hub column with optional optimistic lock.

        Returns True if the write succeeded, False if the optimistic lock
        detected a concurrent update.
        """
        col = self._col(hub_name)
        await self._ensure_row(user_id)

        pool = await get_pool()
        async with pool.acquire() as conn:
            if expected_updated_at is not None:
                tag = await conn.execute(
                    f"UPDATE user_preferences SET {col} = $2::jsonb, updated_at = NOW() "  # noqa: S608
                    "WHERE user_id = $1 AND updated_at = $3",
                    user_id,
                    json.dumps(data),
                    expected_updated_at,
                )
                return tag == "UPDATE 1"
            else:
                await conn.execute(
                    f"UPDATE user_preferences SET {col} = $2::jsonb, updated_at = NOW() "  # noqa: S608
                    "WHERE user_id = $1",
                    user_id,
                    json.dumps(data),
                )
                return True

    async def merge_hub_data(self, user_id: str, hub_name: str, partial_data: dict[str, Any]) -> None:
        """Atomic merge into a hub column using COALESCE + || operator.

        Creates the row on first access via UPSERT.
        """
        col = self._col(hub_name)
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO user_preferences (user_id, {col}) "  # noqa: S608
                f"VALUES ($1, $2::jsonb) "
                f"ON CONFLICT (user_id) DO UPDATE "
                f"SET {col} = COALESCE(user_preferences.{col}, '{{}}'::jsonb) || $2::jsonb, "
                "    updated_at = NOW()",
                user_id,
                json.dumps(partial_data),
            )

    # -- convenience wrappers --------------------------------------------------

    async def get_staging(self, user_id: str) -> dict[str, Any]:
        return await self.get_hub_data(user_id, "staging")

    async def save_staging(self, user_id: str, data: dict[str, Any]) -> None:
        await self.merge_hub_data(user_id, "staging", data)

    async def get_evidence(self, user_id: str) -> dict[str, Any]:
        return await self.get_hub_data(user_id, "evidence")

    async def save_evidence(self, user_id: str, data: dict[str, Any]) -> None:
        await self.merge_hub_data(user_id, "evidence", data)
