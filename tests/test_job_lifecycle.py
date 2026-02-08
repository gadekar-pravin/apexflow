"""Job lifecycle tests -- CRUD, dynamic SET, FK cascade, try_claim dedup.

Tests JobStore + JobRunStore: dynamic update column building, ON DELETE CASCADE
from jobs to job_runs, and try_claim dedup via INSERT ON CONFLICT DO NOTHING.
Requires a real database. Tests are skipped when DB is unavailable.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
class TestJobLifecycle:
    """Verify JobStore and JobRunStore lifecycle behavior."""

    async def test_create_and_get_roundtrip(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Create a job and verify defaults."""
        from core.stores.job_store import JobStore

        with patch("core.stores.job_store.get_pool", AsyncMock(return_value=db_pool)):
            store = JobStore()
            result = await store.create(
                test_user_id,
                "j-1",
                name="Test Job",
                cron_expression="0 * * * *",
                query="run test",
            )
            assert result["id"] == "j-1"
            assert result["enabled"] is True
            assert result["agent_type"] == "PlannerAgent"

            fetched = await store.get(test_user_id, "j-1")
            assert fetched is not None
            assert fetched["name"] == "Test Job"

    async def test_update_dynamic_set(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Dynamic SET clause updates only specified columns."""
        from core.stores.job_store import JobStore

        with patch("core.stores.job_store.get_pool", AsyncMock(return_value=db_pool)):
            store = JobStore()
            await store.create(test_user_id, "j-2", name="Original", cron_expression="0 * * * *", query="q")
            await store.update(test_user_id, "j-2", name="Updated", enabled=False)

            fetched = await store.get(test_user_id, "j-2")
            assert fetched is not None
            assert fetched["name"] == "Updated"
            assert fetched["enabled"] is False
            assert fetched["cron_expression"] == "0 * * * *"

    async def test_update_invalid_column_raises(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Invalid column names are rejected."""
        from core.stores.job_store import JobStore

        with patch("core.stores.job_store.get_pool", AsyncMock(return_value=db_pool)):
            store = JobStore()
            await store.create(test_user_id, "j-3", name="Job", cron_expression="0 * * * *", query="q")
            with pytest.raises(ValueError, match="Invalid columns"):
                await store.update(test_user_id, "j-3", id="hacked")

    async def test_delete_cascades_to_job_runs(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Deleting a job cascades to its job_runs."""
        from core.stores.job_run_store import JobRunStore
        from core.stores.job_store import JobStore

        with (
            patch("core.stores.job_store.get_pool", AsyncMock(return_value=db_pool)),
            patch("core.stores.job_run_store.get_pool", AsyncMock(return_value=db_pool)),
        ):
            job_store = JobStore()
            run_store = JobRunStore()

            await job_store.create(test_user_id, "j-4", name="Cascade", cron_expression="0 * * * *", query="q")
            sched = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
            await run_store.try_claim(test_user_id, "j-4", sched)

            await job_store.delete(test_user_id, "j-4")

            # Job runs should be gone
            async with db_pool.acquire() as conn:
                count = await conn.fetchval("SELECT COUNT(*) FROM job_runs WHERE job_id = $1", "j-4")
            assert count == 0

    async def test_try_claim_first_wins(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """First try_claim returns True, second returns False (ON CONFLICT DO NOTHING)."""
        from core.stores.job_run_store import JobRunStore
        from core.stores.job_store import JobStore

        with (
            patch("core.stores.job_store.get_pool", AsyncMock(return_value=db_pool)),
            patch("core.stores.job_run_store.get_pool", AsyncMock(return_value=db_pool)),
        ):
            job_store = JobStore()
            run_store = JobRunStore()

            await job_store.create(test_user_id, "j-5", name="Dedup", cron_expression="0 * * * *", query="q")
            sched = datetime(2025, 7, 1, 12, 0, 0, tzinfo=UTC)
            assert await run_store.try_claim(test_user_id, "j-5", sched) is True
            assert await run_store.try_claim(test_user_id, "j-5", sched) is False

    async def test_complete_and_recent(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """complete() updates status and recent() lists runs."""
        from core.stores.job_run_store import JobRunStore
        from core.stores.job_store import JobStore

        with (
            patch("core.stores.job_store.get_pool", AsyncMock(return_value=db_pool)),
            patch("core.stores.job_run_store.get_pool", AsyncMock(return_value=db_pool)),
        ):
            job_store = JobStore()
            run_store = JobRunStore()

            await job_store.create(test_user_id, "j-6", name="Complete", cron_expression="0 * * * *", query="q")
            sched = datetime(2025, 8, 1, 12, 0, 0, tzinfo=UTC)
            await run_store.try_claim(test_user_id, "j-6", sched)
            await run_store.complete(test_user_id, "j-6", sched, "completed", output="All done")

            runs = await run_store.recent(test_user_id, "j-6")
            assert len(runs) == 1
            assert runs[0]["status"] == "completed"
            assert runs[0]["output"] == "All done"
            assert runs[0]["completed_at"] is not None

    async def test_load_all_and_delete(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """load_all returns all jobs; delete returns True/False correctly."""
        from core.stores.job_store import JobStore

        with patch("core.stores.job_store.get_pool", AsyncMock(return_value=db_pool)):
            store = JobStore()
            await store.create(test_user_id, "j-7a", name="Job A", cron_expression="0 * * * *", query="q")
            await store.create(test_user_id, "j-7b", name="Job B", cron_expression="0 * * * *", query="q")

            all_jobs = await store.load_all(test_user_id)
            assert len(all_jobs) == 2

            assert await store.delete(test_user_id, "j-7a") is True
            assert await store.delete(test_user_id, "j-7a") is False

            remaining = await store.load_all(test_user_id)
            assert len(remaining) == 1

    async def test_update_metadata_jsonb(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Dynamic update handles metadata JSONB correctly."""
        from core.stores.job_store import JobStore

        with patch("core.stores.job_store.get_pool", AsyncMock(return_value=db_pool)):
            store = JobStore()
            await store.create(test_user_id, "j-8", name="Meta", cron_expression="0 * * * *", query="q")
            await store.update(test_user_id, "j-8", metadata={"key": "value"})

            fetched = await store.get(test_user_id, "j-8")
            assert fetched is not None
            raw = fetched["metadata"]
            meta = json.loads(raw) if isinstance(raw, str) else raw
            assert meta["key"] == "value"
