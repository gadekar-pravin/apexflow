"""Tenant isolation tests -- verify user_id scoping across all stores.

Requires a real database. Tests are skipped when DB is unavailable.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

_rng = np.random.default_rng(42)

USER_A = "tenant-user-a"
USER_B = "tenant-user-b"


# ---------------------------------------------------------------------------
# SessionStore
# ---------------------------------------------------------------------------


class TestSessionTenantIsolation:
    @pytest.mark.asyncio
    async def test_session_isolation(self, db_pool, clean_tables) -> None:  # type: ignore[no-untyped-def]
        from core.stores.session_store import SessionStore

        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=db_pool)):
            store = SessionStore()
            await store.create(USER_A, "s-a1", "query A")

            # User A can read it
            result = await store.get(USER_A, "s-a1")
            assert result is not None
            assert result["id"] == "s-a1"

            # User B cannot
            result = await store.get(USER_B, "s-a1")
            assert result is None

            # User B list is empty
            sessions = await store.list_sessions(USER_B)
            assert len(sessions) == 0

            # User A list has one
            sessions = await store.list_sessions(USER_A)
            assert len(sessions) == 1


# ---------------------------------------------------------------------------
# JobStore
# ---------------------------------------------------------------------------


class TestJobTenantIsolation:
    @pytest.mark.asyncio
    async def test_job_isolation(self, db_pool, clean_tables) -> None:  # type: ignore[no-untyped-def]
        from core.stores.job_store import JobStore

        with patch("core.stores.job_store.get_pool", AsyncMock(return_value=db_pool)):
            store = JobStore()
            await store.create(
                USER_A,
                "j-a1",
                name="Job A",
                cron_expression="0 * * * *",
                query="do A",
            )

            # User A can read it
            result = await store.get(USER_A, "j-a1")
            assert result is not None

            # User B cannot
            result = await store.get(USER_B, "j-a1")
            assert result is None

            # User B list is empty
            jobs = await store.load_all(USER_B)
            assert len(jobs) == 0


# ---------------------------------------------------------------------------
# NotificationStore
# ---------------------------------------------------------------------------


class TestNotificationTenantIsolation:
    @pytest.mark.asyncio
    async def test_notification_isolation(self, db_pool, clean_tables) -> None:  # type: ignore[no-untyped-def]
        from core.stores.notification_store import NotificationStore

        with patch("core.stores.notification_store.get_pool", AsyncMock(return_value=db_pool)):
            store = NotificationStore()
            await store.create(USER_A, source="test", title="Hello", body="World")

            # User A sees it
            notifs = await store.list(USER_A)
            assert len(notifs) == 1

            # User B does not
            notifs = await store.list(USER_B)
            assert len(notifs) == 0


# ---------------------------------------------------------------------------
# ChatStore
# ---------------------------------------------------------------------------


class TestChatTenantIsolation:
    @pytest.mark.asyncio
    async def test_chat_isolation(self, db_pool, clean_tables) -> None:  # type: ignore[no-untyped-def]
        from core.stores.chat_store import ChatStore

        with patch("core.stores.chat_store.get_pool", AsyncMock(return_value=db_pool)):
            store = ChatStore()
            session = await store.create_session(USER_A, "rag", "doc1")
            sid = session["id"]

            # User A can read it
            result = await store.get_session(USER_A, sid)
            assert result is not None

            # User B cannot
            result = await store.get_session(USER_B, sid)
            assert result is None

            # User B list is empty
            sessions = await store.list_sessions(USER_B)
            assert len(sessions) == 0


# ---------------------------------------------------------------------------
# MemoryStore
# ---------------------------------------------------------------------------


class TestMemoryTenantIsolation:
    @pytest.mark.asyncio
    async def test_memory_isolation(self, db_pool, clean_tables) -> None:  # type: ignore[no-untyped-def]
        from core.stores.memory_store import MemoryStore

        with patch("core.stores.memory_store.get_pool", AsyncMock(return_value=db_pool)):
            store = MemoryStore()
            embedding = _rng.random(768).astype(np.float32)
            await store.add(
                USER_A,
                text="User A memory",
                category="general",
                source="test",
                embedding=embedding,
            )

            # User A sees it
            memories = await store.get_all(USER_A)
            assert len(memories) == 1

            # User B does not
            memories = await store.get_all(USER_B)
            assert len(memories) == 0

            # User B search returns nothing
            query_emb = _rng.random(768).astype(np.float32)
            results = await store.search(USER_B, query_emb, limit=10)
            assert len(results) == 0


# ---------------------------------------------------------------------------
# PreferencesStore
# ---------------------------------------------------------------------------


class TestPreferencesTenantIsolation:
    @pytest.mark.asyncio
    async def test_preferences_isolation(self, db_pool, clean_tables) -> None:  # type: ignore[no-untyped-def]
        from core.stores.preferences_store import PreferencesStore

        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=db_pool)):
            store = PreferencesStore()
            await store.merge_hub_data(USER_A, "preferences", {"theme": "dark"})

            # User A reads it
            data = await store.get_hub_data(USER_A, "preferences")
            assert data.get("theme") == "dark"

            # User B gets empty
            data = await store.get_hub_data(USER_B, "preferences")
            assert data == {}


# ---------------------------------------------------------------------------
# StateStore
# ---------------------------------------------------------------------------


class TestStateTenantIsolation:
    @pytest.mark.asyncio
    async def test_state_isolation(self, db_pool, clean_tables) -> None:  # type: ignore[no-untyped-def]
        from core.stores.state_store import StateStore

        with patch("core.stores.state_store.get_pool", AsyncMock(return_value=db_pool)):
            store = StateStore()
            await store.set(USER_A, "my_key", {"value": 42})

            # User A reads it
            data = await store.get(USER_A, "my_key")
            assert data == {"value": 42}

            # User B gets None
            data = await store.get(USER_B, "my_key")
            assert data is None


# ---------------------------------------------------------------------------
# DocumentStore
# ---------------------------------------------------------------------------


class TestDocumentTenantIsolation:
    @pytest.mark.asyncio
    async def test_document_isolation(self, db_pool, clean_tables) -> None:  # type: ignore[no-untyped-def]
        from core.stores.document_store import DocumentStore

        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=db_pool)):
            store = DocumentStore()
            embedding = _rng.random(768).astype(np.float32)
            await store.index_document(
                USER_A,
                filename="test.txt",
                content="Hello world from user A",
                chunks=["Hello world from user A"],
                embeddings=[embedding],
            )

            # User A sees it
            docs = await store.list_documents(USER_A)
            assert len(docs) == 1

            # User B does not
            docs = await store.list_documents(USER_B)
            assert len(docs) == 0
