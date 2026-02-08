"""Tests for Phase 3 store classes -- mock asyncpg pool."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers: mock pool
# ---------------------------------------------------------------------------


def _mock_pool(
    fetchrow: Any = None,
    fetch: Any = None,
    fetchval: Any = None,
    execute: Any = None,
) -> AsyncMock:
    """Create a mock asyncpg pool with a mock connection."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow)
    conn.fetch = AsyncMock(return_value=fetch or [])
    conn.fetchval = AsyncMock(return_value=fetchval)
    conn.execute = AsyncMock(return_value=execute or "UPDATE 1")

    # transaction context manager
    txn = AsyncMock()
    txn.__aenter__ = AsyncMock(return_value=txn)
    txn.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=txn)

    pool = AsyncMock()
    acq = AsyncMock()
    acq.__aenter__ = AsyncMock(return_value=conn)
    acq.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=acq)

    return pool


# ---------------------------------------------------------------------------
# SessionStore
# ---------------------------------------------------------------------------


class TestSessionStore:
    @pytest.mark.asyncio
    async def test_create(self) -> None:
        from core.stores.session_store import SessionStore

        row: dict[str, Any] = {
            "id": "s1",
            "user_id": "u1",
            "query": "hello",
            "status": "running",
            "agent_type": None,
            "graph_data": {},
            "node_outputs": {},
            "cost": Decimal("0"),
            "model_used": None,
            "error": None,
            "created_at": datetime.now(UTC),
            "completed_at": None,
            "remme_scanned": False,
            "metadata": {},
        }
        pool = _mock_pool(fetchrow=row)
        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=pool)):
            store = SessionStore()
            result = await store.create("u1", "s1", "hello")
            assert result["id"] == "s1"
            assert result["user_id"] == "u1"

    @pytest.mark.asyncio
    async def test_get_returns_none_for_wrong_user(self) -> None:
        from core.stores.session_store import SessionStore

        pool = _mock_pool(fetchrow=None)
        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=pool)):
            store = SessionStore()
            result = await store.get("user-b", "s1")
            assert result is None

    @pytest.mark.asyncio
    async def test_list(self) -> None:
        from core.stores.session_store import SessionStore

        rows = [
            {
                "id": "s1",
                "query": "q1",
                "status": "completed",
                "agent_type": None,
                "cost": Decimal("0.001"),
                "model_used": None,
                "created_at": datetime.now(UTC),
                "completed_at": datetime.now(UTC),
            },
        ]
        pool = _mock_pool(fetch=rows)
        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=pool)):
            store = SessionStore()
            result = await store.list_sessions("u1")
            assert len(result) == 1
            assert result[0]["id"] == "s1"

    @pytest.mark.asyncio
    async def test_update_cost_increments(self) -> None:
        from core.stores.session_store import SessionStore

        pool = _mock_pool()
        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=pool)):
            store = SessionStore()
            await store.update_cost("u1", "s1", 0.005)
            # Verify execute was called with increment
            conn = pool.acquire().__aenter__.return_value
            assert conn.execute.called

    @pytest.mark.asyncio
    async def test_mark_scanned_uses_transaction(self) -> None:
        from core.stores.session_store import SessionStore

        pool = _mock_pool()
        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=pool)):
            store = SessionStore()
            await store.mark_scanned("u1", "s1")
            conn = pool.acquire().__aenter__.return_value
            # Should have called transaction()
            assert conn.transaction.called

    @pytest.mark.asyncio
    async def test_get_dashboard_stats(self) -> None:
        from core.stores.session_store import SessionStore

        row = {
            "total_runs": 10,
            "completed": 8,
            "failed": 1,
            "cancelled": 0,
            "running": 1,
            "total_cost": Decimal("0.05"),
            "avg_cost": Decimal("0.005"),
        }
        pool = _mock_pool(fetchrow=row)
        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=pool)):
            store = SessionStore()
            result = await store.get_dashboard_stats("u1", 30)
            assert result["total_runs"] == 10
            assert isinstance(result["total_cost"], float)

    @pytest.mark.asyncio
    async def test_get_daily_stats(self) -> None:
        from core.stores.session_store import SessionStore

        rows = [
            {"date": "2026-01-01", "runs": 5, "cost": Decimal("0.01"), "completed": 4, "failed": 1},
        ]
        pool = _mock_pool(fetch=rows)
        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=pool)):
            store = SessionStore()
            result = await store.get_daily_stats("u1", 30)
            assert len(result) == 1


# ---------------------------------------------------------------------------
# JobStore
# ---------------------------------------------------------------------------


class TestJobStore:
    @pytest.mark.asyncio
    async def test_create_and_load(self) -> None:
        from core.stores.job_store import JobStore

        row: dict[str, Any] = {
            "id": "j1",
            "user_id": "u1",
            "name": "test",
            "cron_expression": "* * * * *",
            "agent_type": "PlannerAgent",
            "query": "do stuff",
            "skill_id": None,
            "enabled": True,
            "last_run": None,
            "next_run": None,
            "last_output": None,
            "created_at": datetime.now(UTC),
            "metadata": {},
        }
        pool = _mock_pool(fetchrow=row, fetch=[row])
        with patch("core.stores.job_store.get_pool", AsyncMock(return_value=pool)):
            store = JobStore()
            created = await store.create("u1", "j1", name="test", cron_expression="* * * * *", query="do stuff")
            assert created["id"] == "j1"
            all_jobs = await store.load_all("u1")
            assert len(all_jobs) == 1

    @pytest.mark.asyncio
    async def test_delete(self) -> None:
        from core.stores.job_store import JobStore

        pool = _mock_pool(execute="DELETE 1")
        with patch("core.stores.job_store.get_pool", AsyncMock(return_value=pool)):
            store = JobStore()
            result = await store.delete("u1", "j1")
            assert result is True


# ---------------------------------------------------------------------------
# JobRunStore
# ---------------------------------------------------------------------------


class TestJobRunStore:
    @pytest.mark.asyncio
    async def test_try_claim_success(self) -> None:
        from core.stores.job_run_store import JobRunStore

        pool = _mock_pool(execute="INSERT 0 1")
        with patch("core.stores.job_run_store.get_pool", AsyncMock(return_value=pool)):
            store = JobRunStore()
            result = await store.try_claim("u1", "j1", datetime.now(UTC))
            assert result is True

    @pytest.mark.asyncio
    async def test_try_claim_dedup(self) -> None:
        from core.stores.job_run_store import JobRunStore

        pool = _mock_pool(execute="INSERT 0 0")
        with patch("core.stores.job_run_store.get_pool", AsyncMock(return_value=pool)):
            store = JobRunStore()
            result = await store.try_claim("u1", "j1", datetime.now(UTC))
            assert result is False


# ---------------------------------------------------------------------------
# NotificationStore
# ---------------------------------------------------------------------------


class TestNotificationStore:
    @pytest.mark.asyncio
    async def test_create(self) -> None:
        from core.stores.notification_store import NotificationStore

        pool = _mock_pool()
        with patch("core.stores.notification_store.get_pool", AsyncMock(return_value=pool)):
            store = NotificationStore()
            notif_id = await store.create("u1", source="test", title="hi", body="hello")
            assert isinstance(notif_id, str)
            assert len(notif_id) > 0

    @pytest.mark.asyncio
    async def test_mark_read(self) -> None:
        from core.stores.notification_store import NotificationStore

        pool = _mock_pool(execute="UPDATE 1")
        with patch("core.stores.notification_store.get_pool", AsyncMock(return_value=pool)):
            store = NotificationStore()
            result = await store.mark_read("u1", "n1")
            assert result is True


# ---------------------------------------------------------------------------
# ChatStore
# ---------------------------------------------------------------------------


class TestChatStore:
    @pytest.mark.asyncio
    async def test_create_session(self) -> None:
        from core.stores.chat_store import ChatStore

        row = {
            "id": "cs1",
            "user_id": "u1",
            "target_type": "rag",
            "target_id": "doc1",
            "title": "New Chat",
            "model": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        pool = _mock_pool(fetchrow=row)
        with patch("core.stores.chat_store.get_pool", AsyncMock(return_value=pool)):
            store = ChatStore()
            result = await store.create_session("u1", "rag", "doc1")
            assert result["target_type"] == "rag"

    @pytest.mark.asyncio
    async def test_add_message_uses_transaction(self) -> None:
        from core.stores.chat_store import ChatStore

        msg_row = {
            "id": "m1",
            "session_id": "cs1",
            "user_id": "u1",
            "role": "user",
            "content": "hello",
            "created_at": datetime.now(UTC),
            "metadata": {},
        }
        pool = _mock_pool(fetchrow=msg_row)
        with patch("core.stores.chat_store.get_pool", AsyncMock(return_value=pool)):
            store = ChatStore()
            result = await store.add_message("u1", "cs1", "user", "hello")
            assert result["role"] == "user"
            # Verify transaction was used
            conn = pool.acquire().__aenter__.return_value
            assert conn.transaction.called

    @pytest.mark.asyncio
    async def test_get_messages_chronological(self) -> None:
        from core.stores.chat_store import ChatStore

        rows = [
            {
                "id": "m1",
                "session_id": "cs1",
                "user_id": "u1",
                "role": "user",
                "content": "first",
                "created_at": datetime(2026, 1, 1, tzinfo=UTC),
                "metadata": {},
            },
            {
                "id": "m2",
                "session_id": "cs1",
                "user_id": "u1",
                "role": "assistant",
                "content": "second",
                "created_at": datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
                "metadata": {},
            },
        ]
        pool = _mock_pool(fetch=rows)
        with patch("core.stores.chat_store.get_pool", AsyncMock(return_value=pool)):
            store = ChatStore()
            msgs = await store.get_messages("u1", "cs1")
            assert len(msgs) == 2
            assert msgs[0]["content"] == "first"


# ---------------------------------------------------------------------------
# StateStore
# ---------------------------------------------------------------------------


class TestStateStore:
    @pytest.mark.asyncio
    async def test_get_returns_none_when_missing(self) -> None:
        from core.stores.state_store import StateStore

        pool = _mock_pool(fetchval=None)
        with patch("core.stores.state_store.get_pool", AsyncMock(return_value=pool)):
            store = StateStore()
            result = await store.get("u1", "missing_key")
            assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get(self) -> None:
        from core.stores.state_store import StateStore

        data = {"foo": "bar"}
        pool = _mock_pool(fetchval=json.dumps(data))
        with patch("core.stores.state_store.get_pool", AsyncMock(return_value=pool)):
            store = StateStore()
            await store.set("u1", "k1", data)
            result = await store.get("u1", "k1")
            assert result == data

    @pytest.mark.asyncio
    async def test_user_scoped_keys(self) -> None:
        from core.stores.state_store import StateStore

        # user-a sets a value, user-b gets None
        pool_a = _mock_pool(fetchval=json.dumps({"x": 1}))
        pool_b = _mock_pool(fetchval=None)

        with patch("core.stores.state_store.get_pool", AsyncMock(return_value=pool_a)):
            store = StateStore()
            result_a = await store.get("user-a", "k1")
            assert result_a == {"x": 1}

        with patch("core.stores.state_store.get_pool", AsyncMock(return_value=pool_b)):
            store = StateStore()
            result_b = await store.get("user-b", "k1")
            assert result_b is None
