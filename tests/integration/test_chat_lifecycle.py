"""Chat lifecycle tests -- transaction atomicity, cascading deletes, role check.

Tests ChatStore's add_message atomicity (insert message + update session.updated_at),
ON DELETE CASCADE, and role CHECK constraint enforcement.
Requires a real database. Tests are skipped when DB is unavailable.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest


@pytest.mark.asyncio
class TestChatLifecycle:
    """Verify ChatStore session/message CRUD and transaction atomicity."""

    async def test_create_session_roundtrip(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Create a chat session and verify all fields."""
        from core.stores.chat_store import ChatStore

        with patch("core.stores.chat_store.get_pool", AsyncMock(return_value=db_pool)):
            store = ChatStore()
            session = await store.create_session(
                test_user_id, "rag", "doc-1", title="Test Chat", model="gemini-1.5-flash"
            )
            assert session["target_type"] == "rag"
            assert session["target_id"] == "doc-1"
            assert session["title"] == "Test Chat"
            assert session["model"] == "gemini-1.5-flash"

            fetched = await store.get_session(test_user_id, session["id"])
            assert fetched is not None
            assert fetched["id"] == session["id"]

    async def test_add_message_updates_session_timestamp(
        self, db_pool: Any, clean_tables: None, test_user_id: str
    ) -> None:
        """add_message atomically updates the session's updated_at."""
        from core.stores.chat_store import ChatStore

        with patch("core.stores.chat_store.get_pool", AsyncMock(return_value=db_pool)):
            store = ChatStore()
            session = await store.create_session(test_user_id, "rag", "doc-1")
            original_ts = session["updated_at"]

            await asyncio.sleep(0.05)
            await store.add_message(test_user_id, session["id"], "user", "Hello!")

            updated = await store.get_session(test_user_id, session["id"])
            assert updated is not None
            assert updated["updated_at"] > original_ts

    async def test_add_multiple_messages_chronological_order(
        self, db_pool: Any, clean_tables: None, test_user_id: str
    ) -> None:
        """Messages are returned in chronological order (ASC by created_at)."""
        from core.stores.chat_store import ChatStore

        with patch("core.stores.chat_store.get_pool", AsyncMock(return_value=db_pool)):
            store = ChatStore()
            session = await store.create_session(test_user_id, "rag", "doc-1")
            sid = session["id"]

            await store.add_message(test_user_id, sid, "user", "First")
            await store.add_message(test_user_id, sid, "assistant", "Second")
            await store.add_message(test_user_id, sid, "user", "Third")

            messages = await store.get_messages(test_user_id, sid)
            assert len(messages) == 3
            assert messages[0]["content"] == "First"
            assert messages[1]["content"] == "Second"
            assert messages[2]["content"] == "Third"

    async def test_get_messages_pagination(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """get_messages supports limit/offset."""
        from core.stores.chat_store import ChatStore

        with patch("core.stores.chat_store.get_pool", AsyncMock(return_value=db_pool)):
            store = ChatStore()
            session = await store.create_session(test_user_id, "rag", "doc-1")
            sid = session["id"]

            for i in range(5):
                await store.add_message(test_user_id, sid, "user", f"Message {i}")

            page1 = await store.get_messages(test_user_id, sid, limit=2, offset=0)
            assert len(page1) == 2
            assert page1[0]["content"] == "Message 0"

            page2 = await store.get_messages(test_user_id, sid, limit=2, offset=2)
            assert len(page2) == 2
            assert page2[0]["content"] == "Message 2"

    async def test_cascading_delete_removes_messages(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Deleting a chat session cascades to its messages."""
        from core.stores.chat_store import ChatStore

        with patch("core.stores.chat_store.get_pool", AsyncMock(return_value=db_pool)):
            store = ChatStore()
            session = await store.create_session(test_user_id, "rag", "doc-1")
            sid = session["id"]

            await store.add_message(test_user_id, sid, "user", "Hello")
            await store.add_message(test_user_id, sid, "assistant", "Hi")

            deleted = await store.delete_session(test_user_id, sid)
            assert deleted is True

            # Messages should be gone
            async with db_pool.acquire() as conn:
                count = await conn.fetchval("SELECT COUNT(*) FROM chat_messages WHERE session_id = $1", sid)
            assert count == 0

    async def test_list_sessions_filter_by_target(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """list_sessions filters by target_type + target_id."""
        from core.stores.chat_store import ChatStore

        with patch("core.stores.chat_store.get_pool", AsyncMock(return_value=db_pool)):
            store = ChatStore()
            await store.create_session(test_user_id, "rag", "doc-1")
            await store.create_session(test_user_id, "rag", "doc-2")
            await store.create_session(test_user_id, "agent", "agent-1")

            rag_doc1 = await store.list_sessions(test_user_id, target_type="rag", target_id="doc-1")
            assert len(rag_doc1) == 1

            all_sessions = await store.list_sessions(test_user_id)
            assert len(all_sessions) == 3

    async def test_role_check_constraint(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Invalid role values are rejected by the CHECK constraint."""
        from core.stores.chat_store import ChatStore

        with patch("core.stores.chat_store.get_pool", AsyncMock(return_value=db_pool)):
            store = ChatStore()
            session = await store.create_session(test_user_id, "rag", "doc-1")
            sid = session["id"]

            with pytest.raises(asyncpg.CheckViolationError):
                # Bypass the store to test raw constraint
                async with db_pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO chat_messages (id, session_id, user_id, role, content) "
                        "VALUES ($1, $2, $3, $4, $5)",
                        "m-bad",
                        sid,
                        test_user_id,
                        "admin",
                        "bad role",
                    )

    async def test_message_metadata_jsonb_roundtrip(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Message metadata JSONB roundtrips correctly."""
        from core.stores.chat_store import ChatStore

        with patch("core.stores.chat_store.get_pool", AsyncMock(return_value=db_pool)):
            store = ChatStore()
            session = await store.create_session(test_user_id, "rag", "doc-1")
            sid = session["id"]

            meta = {"tokens": 150, "tool_calls": ["web_search"], "nested": {"key": "value"}}
            await store.add_message(test_user_id, sid, "assistant", "Response", metadata=meta)

            messages = await store.get_messages(test_user_id, sid)
            assert len(messages) == 1
            raw = messages[0]["metadata"]
            actual_meta = json.loads(raw) if isinstance(raw, str) else raw
            assert actual_meta["tokens"] == 150
            assert actual_meta["tool_calls"] == ["web_search"]
            assert actual_meta["nested"]["key"] == "value"

    async def test_delete_nonexistent_returns_false(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Deleting a nonexistent session returns False."""
        from core.stores.chat_store import ChatStore

        with patch("core.stores.chat_store.get_pool", AsyncMock(return_value=db_pool)):
            store = ChatStore()
            assert await store.delete_session(test_user_id, "nonexistent") is False
