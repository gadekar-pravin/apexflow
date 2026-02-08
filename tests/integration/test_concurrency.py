"""Concurrency tests -- verify atomicity and dedup under parallel access.

Requires a real database. Tests are skipped when DB is unavailable.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest


class TestPreferencesConcurrentMerge:
    @pytest.mark.asyncio
    async def test_concurrent_merge_preserves_both_keys(self, db_pool, clean_tables) -> None:  # type: ignore[no-untyped-def]
        """Two concurrent merge_hub_data calls with disjoint keys should both survive."""
        from core.stores.preferences_store import PreferencesStore

        user_id = "concurrent-user"

        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=db_pool)):
            store = PreferencesStore()

            await asyncio.gather(
                store.merge_hub_data(user_id, "preferences", {"key_a": "value_a"}),
                store.merge_hub_data(user_id, "preferences", {"key_b": "value_b"}),
            )

            result = await store.get_hub_data(user_id, "preferences")
            assert result.get("key_a") == "value_a"
            assert result.get("key_b") == "value_b"


class TestJobDedupConcurrentClaims:
    @pytest.mark.asyncio
    async def test_exactly_one_claim_wins(self, db_pool, clean_tables) -> None:  # type: ignore[no-untyped-def]
        """Two concurrent try_claim calls for the same job+timestamp: exactly one wins."""
        from core.stores.job_run_store import JobRunStore
        from core.stores.job_store import JobStore

        user_id = "dedup-user"
        job_id = "dedup-job"
        scheduled = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)

        with (
            patch("core.stores.job_store.get_pool", AsyncMock(return_value=db_pool)),
            patch("core.stores.job_run_store.get_pool", AsyncMock(return_value=db_pool)),
        ):
            # Create the parent job first (FK constraint)
            job_store = JobStore()
            await job_store.create(
                user_id,
                job_id,
                name="Dedup Test",
                cron_expression="0 12 * * *",
                query="test dedup",
            )

            run_store = JobRunStore()
            results = await asyncio.gather(
                run_store.try_claim(user_id, job_id, scheduled),
                run_store.try_claim(user_id, job_id, scheduled),
            )

            assert sorted(results) == [False, True]
