"""Chat store -- sessions + append-only messages."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from core.database import get_pool

logger = logging.getLogger(__name__)


class ChatStore:
    """Stateless data-access object for chat_sessions and chat_messages."""

    # -- sessions -------------------------------------------------------------

    async def list_sessions(
        self,
        user_id: str,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> list[dict[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if target_type and target_id:
                rows = await conn.fetch(
                    """
                    SELECT id, title, model, target_type, target_id,
                           created_at, updated_at
                    FROM chat_sessions
                    WHERE user_id = $1 AND target_type = $2 AND target_id = $3
                    ORDER BY updated_at DESC
                    """,
                    user_id,
                    target_type,
                    target_id,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, title, model, target_type, target_id,
                           created_at, updated_at
                    FROM chat_sessions
                    WHERE user_id = $1
                    ORDER BY updated_at DESC
                    """,
                    user_id,
                )
        return [dict(r) for r in rows]

    async def get_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM chat_sessions WHERE id = $1 AND user_id = $2",
                session_id,
                user_id,
            )
        return dict(row) if row else None

    async def create_session(
        self,
        user_id: str,
        target_type: str,
        target_id: str,
        title: str = "New Chat",
        model: str | None = None,
    ) -> dict[str, Any]:
        session_id = str(uuid.uuid4())
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO chat_sessions (id, user_id, target_type, target_id, title, model)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING *
                """,
                session_id,
                user_id,
                target_type,
                target_id,
                title,
                model,
            )
        return dict(row) if row else {}

    async def delete_session(self, user_id: str, session_id: str) -> bool:
        pool = await get_pool()
        async with pool.acquire() as conn:
            tag = await conn.execute(
                "DELETE FROM chat_sessions WHERE id = $1 AND user_id = $2",
                session_id,
                user_id,
            )
        return tag == "DELETE 1"

    # -- messages (append-only) -----------------------------------------------

    async def add_message(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        msg_id = str(uuid.uuid4())
        pool = await get_pool()
        async with pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                    INSERT INTO chat_messages (id, session_id, user_id, role, content, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                    RETURNING *
                    """,
                msg_id,
                session_id,
                user_id,
                role,
                content,
                json.dumps(metadata or {}),
            )
            await conn.execute(
                """
                    UPDATE chat_sessions SET updated_at = NOW()
                    WHERE id = $1 AND user_id = $2
                    """,
                session_id,
                user_id,
            )
        return dict(row) if row else {}

    async def get_messages(
        self,
        user_id: str,
        session_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM chat_messages
                WHERE session_id = $1 AND user_id = $2
                ORDER BY created_at ASC
                LIMIT $3 OFFSET $4
                """,
                session_id,
                user_id,
                limit,
                offset,
            )
        return [dict(r) for r in rows]
