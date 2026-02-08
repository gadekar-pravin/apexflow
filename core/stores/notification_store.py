"""Notification store -- CRUD for the ``notifications`` table."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from core.database import get_pool

logger = logging.getLogger(__name__)


class NotificationStore:
    """Stateless data-access object for notifications (replaces SQLite inbox)."""

    async def create(
        self,
        user_id: str,
        *,
        source: str,
        title: str,
        body: str,
        priority: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        notif_id = str(uuid.uuid4())
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO notifications (id, user_id, source, title, body, priority, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                """,
                notif_id,
                user_id,
                source,
                title,
                body,
                priority,
                json.dumps(metadata or {}),
            )
        return notif_id

    async def list(
        self,
        user_id: str,
        *,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if unread_only:
                rows = await conn.fetch(
                    """
                    SELECT * FROM notifications
                    WHERE user_id = $1 AND NOT is_read
                    ORDER BY created_at DESC
                    LIMIT $2 OFFSET $3
                    """,
                    user_id,
                    limit,
                    offset,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM notifications
                    WHERE user_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2 OFFSET $3
                    """,
                    user_id,
                    limit,
                    offset,
                )
        return [dict(r) for r in rows]

    async def mark_read(self, user_id: str, notif_id: str) -> bool:
        pool = await get_pool()
        async with pool.acquire() as conn:
            tag = await conn.execute(
                """
                UPDATE notifications SET is_read = TRUE
                WHERE id = $1 AND user_id = $2
                """,
                notif_id,
                user_id,
            )
        return tag == "UPDATE 1"

    async def delete(self, user_id: str, notif_id: str) -> bool:
        pool = await get_pool()
        async with pool.acquire() as conn:
            tag = await conn.execute(
                "DELETE FROM notifications WHERE id = $1 AND user_id = $2",
                notif_id,
                user_id,
            )
        return tag == "DELETE 1"
