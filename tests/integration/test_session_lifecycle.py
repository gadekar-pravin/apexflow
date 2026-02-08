"""Session lifecycle tests -- CRUD, status transitions, aggregation, mark_scanned.

SessionStore is the most complex store with SQL aggregation (COUNT FILTER,
SUM, GROUP BY), atomic mark_scanned transactions, and COALESCE(completed_at, NOW()).
Requires a real database. Tests are skipped when DB is unavailable.
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
class TestSessionLifecycle:
    """Verify SessionStore CRUD, status transitions, and aggregation."""

    async def test_create_and_get_roundtrip(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Create returns defaults: status='running', cost=0, remme_scanned=False."""
        from core.stores.session_store import SessionStore

        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=db_pool)):
            store = SessionStore()
            result = await store.create(test_user_id, "s-1", "test query")

            assert result["id"] == "s-1"
            assert result["status"] == "running"
            assert result["cost"] == Decimal("0")
            assert result["remme_scanned"] is False

            fetched = await store.get(test_user_id, "s-1")
            assert fetched is not None
            assert fetched["query"] == "test query"

    async def test_update_status_sets_completed_at(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Setting status to 'completed' populates completed_at."""
        from core.stores.session_store import SessionStore

        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=db_pool)):
            store = SessionStore()
            await store.create(test_user_id, "s-2", "query")
            await store.update_status(test_user_id, "s-2", "completed")

            session = await store.get(test_user_id, "s-2")
            assert session is not None
            assert session["status"] == "completed"
            assert session["completed_at"] is not None

    async def test_update_status_preserves_first_completed_at(
        self, db_pool: Any, clean_tables: None, test_user_id: str
    ) -> None:
        """COALESCE(completed_at, NOW()) prevents overwriting the first timestamp."""
        from core.stores.session_store import SessionStore

        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=db_pool)):
            store = SessionStore()
            await store.create(test_user_id, "s-3", "query")
            await store.update_status(test_user_id, "s-3", "completed")

            first = await store.get(test_user_id, "s-3")
            assert first is not None
            first_ts = first["completed_at"]

            # Small delay to ensure NOW() would differ
            await asyncio.sleep(0.05)
            await store.update_status(test_user_id, "s-3", "failed")

            second = await store.get(test_user_id, "s-3")
            assert second is not None
            assert second["completed_at"] == first_ts

    async def test_update_cost_accumulates(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """cost = cost + delta accumulates with Decimal precision."""
        from core.stores.session_store import SessionStore

        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=db_pool)):
            store = SessionStore()
            await store.create(test_user_id, "s-4", "query")
            await store.update_cost(test_user_id, "s-4", 0.001)
            await store.update_cost(test_user_id, "s-4", 0.002)

            session = await store.get(test_user_id, "s-4")
            assert session is not None
            assert session["cost"] == Decimal("0.003000")

    async def test_update_graph_jsonb(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Complex nested JSONB roundtrips correctly."""
        from core.stores.session_store import SessionStore

        graph = {
            "nodes": [{"id": "n1", "type": "planner"}, {"id": "n2", "type": "coder"}],
            "edges": [{"from": "n1", "to": "n2"}],
        }
        outputs = {"n1": {"result": "plan created", "tokens": 500}}

        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=db_pool)):
            store = SessionStore()
            await store.create(test_user_id, "s-5", "query")
            await store.update_graph(test_user_id, "s-5", graph, outputs)

            session = await store.get(test_user_id, "s-5")
            assert session is not None
            gd = session["graph_data"]
            if isinstance(gd, str):
                gd = json.loads(gd)
            assert len(gd["nodes"]) == 2
            assert gd["edges"][0]["from"] == "n1"

    async def test_mark_scanned_atomic_transaction(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """mark_scanned atomically updates sessions AND inserts scanned_runs."""
        from core.stores.session_store import SessionStore

        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=db_pool)):
            store = SessionStore()
            await store.create(test_user_id, "s-6", "query")
            await store.update_status(test_user_id, "s-6", "completed")
            await store.mark_scanned(test_user_id, "s-6")

            session = await store.get(test_user_id, "s-6")
            assert session is not None
            assert session["remme_scanned"] is True

            # Verify scanned_runs row
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow("SELECT * FROM scanned_runs WHERE run_id = $1", "s-6")
            assert row is not None
            assert row["user_id"] == test_user_id

    async def test_mark_scanned_idempotent(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Second mark_scanned call doesn't duplicate scanned_runs (ON CONFLICT DO NOTHING)."""
        from core.stores.session_store import SessionStore

        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=db_pool)):
            store = SessionStore()
            await store.create(test_user_id, "s-7", "query")
            await store.update_status(test_user_id, "s-7", "completed")

            await store.mark_scanned(test_user_id, "s-7")
            await store.mark_scanned(test_user_id, "s-7")

            async with db_pool.acquire() as conn:
                count = await conn.fetchval("SELECT COUNT(*) FROM scanned_runs WHERE run_id = $1", "s-7")
            assert count == 1

    async def test_list_sessions_with_status_filter(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """list_sessions filters by status correctly."""
        from core.stores.session_store import SessionStore

        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=db_pool)):
            store = SessionStore()
            await store.create(test_user_id, "s-a", "query a")
            await store.create(test_user_id, "s-b", "query b")
            await store.update_status(test_user_id, "s-a", "completed")

            completed = await store.list_sessions(test_user_id, status="completed")
            assert len(completed) == 1
            assert completed[0]["id"] == "s-a"

            running = await store.list_sessions(test_user_id, status="running")
            assert len(running) == 1
            assert running[0]["id"] == "s-b"

    async def test_list_sessions_pagination(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """list_sessions supports limit/offset, ordered DESC by created_at."""
        from core.stores.session_store import SessionStore

        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=db_pool)):
            store = SessionStore()
            for i in range(5):
                await store.create(test_user_id, f"s-page-{i}", f"query {i}")

            page1 = await store.list_sessions(test_user_id, limit=2, offset=0)
            assert len(page1) == 2

            page2 = await store.list_sessions(test_user_id, limit=2, offset=2)
            assert len(page2) == 2

            page3 = await store.list_sessions(test_user_id, limit=2, offset=4)
            assert len(page3) == 1

            # No overlap between pages
            page1_ids = {s["id"] for s in page1}
            page2_ids = {s["id"] for s in page2}
            assert page1_ids.isdisjoint(page2_ids)

    async def test_list_unscanned_excludes_running_and_scanned(
        self, db_pool: Any, clean_tables: None, test_user_id: str
    ) -> None:
        """list_unscanned only returns completed/failed sessions that are NOT scanned."""
        from core.stores.session_store import SessionStore

        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=db_pool)):
            store = SessionStore()
            # running — excluded (still running)
            await store.create(test_user_id, "s-run", "running query")
            # completed + unscanned — included
            await store.create(test_user_id, "s-comp", "completed query")
            await store.update_status(test_user_id, "s-comp", "completed")
            # completed + scanned — excluded
            await store.create(test_user_id, "s-scanned", "scanned query")
            await store.update_status(test_user_id, "s-scanned", "completed")
            await store.mark_scanned(test_user_id, "s-scanned")
            # failed + unscanned — included
            await store.create(test_user_id, "s-fail", "failed query")
            await store.update_status(test_user_id, "s-fail", "failed")

            unscanned = await store.list_unscanned(test_user_id)
            ids = {s["id"] for s in unscanned}
            assert ids == {"s-comp", "s-fail"}

    async def test_dashboard_stats_aggregation(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Dashboard stats use COUNT FILTER and SUM correctly across mixed statuses."""
        from core.stores.session_store import SessionStore

        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=db_pool)):
            store = SessionStore()
            # 2 completed, 1 failed, 1 running
            await store.create(test_user_id, "s-d1", "q1")
            await store.update_status(test_user_id, "s-d1", "completed")
            await store.update_cost(test_user_id, "s-d1", 0.01)

            await store.create(test_user_id, "s-d2", "q2")
            await store.update_status(test_user_id, "s-d2", "completed")
            await store.update_cost(test_user_id, "s-d2", 0.02)

            await store.create(test_user_id, "s-d3", "q3")
            await store.update_status(test_user_id, "s-d3", "failed")

            await store.create(test_user_id, "s-d4", "q4")

            stats = await store.get_dashboard_stats(test_user_id)
            assert stats["total_runs"] == 4
            assert stats["completed"] == 2
            assert stats["failed"] == 1
            assert stats["running"] == 1
            assert abs(stats["total_cost"] - 0.03) < 1e-6

    async def test_daily_stats_groups_by_date(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Daily stats groups by DATE(created_at)."""
        from core.stores.session_store import SessionStore

        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=db_pool)):
            store = SessionStore()
            await store.create(test_user_id, "s-daily-1", "q1")
            await store.update_status(test_user_id, "s-daily-1", "completed")
            await store.create(test_user_id, "s-daily-2", "q2")

            stats = await store.get_daily_stats(test_user_id)
            # All created today, so should be exactly 1 date bucket
            assert len(stats) == 1
            assert stats[0]["runs"] == 2
            assert stats[0]["completed"] == 1

    async def test_delete_session(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Delete returns True and removes the session."""
        from core.stores.session_store import SessionStore

        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=db_pool)):
            store = SessionStore()
            await store.create(test_user_id, "s-del", "delete me")
            assert await store.delete(test_user_id, "s-del") is True
            assert await store.get(test_user_id, "s-del") is None
            assert await store.delete(test_user_id, "s-del") is False

    async def test_exists_true_and_false(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """exists() returns correct boolean."""
        from core.stores.session_store import SessionStore

        with patch("core.stores.session_store.get_pool", AsyncMock(return_value=db_pool)):
            store = SessionStore()
            await store.create(test_user_id, "s-exists", "query")
            assert await store.exists(test_user_id, "s-exists") is True
            assert await store.exists(test_user_id, "s-nope") is False
