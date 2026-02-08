"""Preferences optimistic locking tests -- JSONB merge, hub allowlist, concurrent writes.

Tests PreferencesStore's optimistic locking via expected_updated_at,
JSONB merge semantics (COALESCE || operator), and hub column allowlist.
Requires a real database. Tests are skipped when DB is unavailable.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
class TestPreferencesOptimisticLock:
    """Verify PreferencesStore locking, merge, and hub column behavior."""

    async def test_save_hub_data_full_overwrite(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """save_hub_data replaces (not merges) the column value."""
        from core.stores.preferences_store import PreferencesStore

        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=db_pool)):
            store = PreferencesStore()
            await store.save_hub_data(test_user_id, "preferences", {"theme": "dark", "lang": "en"})
            await store.save_hub_data(test_user_id, "preferences", {"theme": "light"})

            data = await store.get_hub_data(test_user_id, "preferences")
            # Full overwrite: lang should be gone
            assert data == {"theme": "light"}

    async def test_merge_hub_data_partial_update(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """merge_hub_data preserves existing keys while adding new ones."""
        from core.stores.preferences_store import PreferencesStore

        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=db_pool)):
            store = PreferencesStore()
            await store.merge_hub_data(test_user_id, "preferences", {"theme": "dark"})
            await store.merge_hub_data(test_user_id, "preferences", {"lang": "en"})

            data = await store.get_hub_data(test_user_id, "preferences")
            assert data["theme"] == "dark"
            assert data["lang"] == "en"

    async def test_merge_hub_data_overwrites_existing_key(
        self, db_pool: Any, clean_tables: None, test_user_id: str
    ) -> None:
        """JSONB || operator: right-side wins for overlapping keys."""
        from core.stores.preferences_store import PreferencesStore

        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=db_pool)):
            store = PreferencesStore()
            await store.merge_hub_data(test_user_id, "preferences", {"theme": "dark", "font_size": 14})
            await store.merge_hub_data(test_user_id, "preferences", {"theme": "light"})

            data = await store.get_hub_data(test_user_id, "preferences")
            assert data["theme"] == "light"
            assert data["font_size"] == 14

    async def test_optimistic_lock_succeeds_with_matching_timestamp(
        self, db_pool: Any, clean_tables: None, test_user_id: str
    ) -> None:
        """save_hub_data with correct expected_updated_at succeeds."""
        from core.stores.preferences_store import PreferencesStore

        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=db_pool)):
            store = PreferencesStore()
            await store.save_hub_data(test_user_id, "preferences", {"v": 1})

            # Read the current updated_at
            async with db_pool.acquire() as conn:
                ts = await conn.fetchval(
                    "SELECT updated_at FROM user_preferences WHERE user_id = $1",
                    test_user_id,
                )

            ok = await store.save_hub_data(test_user_id, "preferences", {"v": 2}, expected_updated_at=ts)
            assert ok is True

            data = await store.get_hub_data(test_user_id, "preferences")
            assert data["v"] == 2

    async def test_optimistic_lock_fails_with_stale_timestamp(
        self, db_pool: Any, clean_tables: None, test_user_id: str
    ) -> None:
        """save_hub_data with stale expected_updated_at returns False, data unchanged."""
        from core.stores.preferences_store import PreferencesStore

        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=db_pool)):
            store = PreferencesStore()
            await store.save_hub_data(test_user_id, "preferences", {"v": 1})

            # Read the timestamp
            async with db_pool.acquire() as conn:
                old_ts = await conn.fetchval(
                    "SELECT updated_at FROM user_preferences WHERE user_id = $1",
                    test_user_id,
                )

            # Advance updated_at by doing another write
            await asyncio.sleep(0.05)
            await store.save_hub_data(test_user_id, "preferences", {"v": 2})

            # Now try with the stale timestamp
            ok = await store.save_hub_data(test_user_id, "preferences", {"v": 3}, expected_updated_at=old_ts)
            assert ok is False

            # Data should still be v=2
            data = await store.get_hub_data(test_user_id, "preferences")
            assert data["v"] == 2

    async def test_hubs_are_independent(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Writing to one hub doesn't clobber another."""
        from core.stores.preferences_store import PreferencesStore

        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=db_pool)):
            store = PreferencesStore()
            await store.merge_hub_data(test_user_id, "preferences", {"theme": "dark"})
            await store.merge_hub_data(test_user_id, "operating_context", {"timezone": "UTC"})

            prefs = await store.get_hub_data(test_user_id, "preferences")
            ctx = await store.get_hub_data(test_user_id, "operating_context")
            assert prefs == {"theme": "dark"}
            assert ctx == {"timezone": "UTC"}

    async def test_invalid_hub_name_raises_value_error(
        self, db_pool: Any, clean_tables: None, test_user_id: str
    ) -> None:
        """Unknown hub name raises ValueError (allowlist enforcement)."""
        from core.stores.preferences_store import PreferencesStore

        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=db_pool)):
            store = PreferencesStore()
            with pytest.raises(ValueError, match="Unknown hub name"):
                await store.get_hub_data(test_user_id, "nonexistent_hub")

    async def test_merge_creates_row_on_first_access(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """merge_hub_data creates the user_preferences row via UPSERT on first access."""
        from core.stores.preferences_store import PreferencesStore

        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=db_pool)):
            store = PreferencesStore()
            # No row exists yet — merge should create one
            await store.merge_hub_data(test_user_id, "preferences", {"created": True})

            data = await store.get_hub_data(test_user_id, "preferences")
            assert data["created"] is True

    async def test_all_five_hubs_writable(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """All 5 hub columns accept writes and reads."""
        from core.stores.preferences_store import PreferencesStore

        hubs: dict[str, dict[str, Any]] = {
            "preferences": {"theme": "dark"},
            "operating_context": {"timezone": "EST"},
            "soft_identity": {"name": "test"},
            "evidence": {"entries": []},
            "staging": {"queue": []},
        }

        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=db_pool)):
            store = PreferencesStore()
            for hub_name, data in hubs.items():
                await store.merge_hub_data(test_user_id, hub_name, data)

            for hub_name, expected in hubs.items():
                actual = await store.get_hub_data(test_user_id, hub_name)
                assert actual == expected, f"Hub {hub_name}: expected {expected}, got {actual}"

    async def test_convenience_wrappers_staging_and_evidence(
        self, db_pool: Any, clean_tables: None, test_user_id: str
    ) -> None:
        """get_staging/save_staging and get_evidence/save_evidence work correctly."""
        from core.stores.preferences_store import PreferencesStore

        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=db_pool)):
            store = PreferencesStore()

            await store.save_staging(test_user_id, {"pending": ["item1"]})
            staging = await store.get_staging(test_user_id)
            assert staging["pending"] == ["item1"]

            await store.save_evidence(test_user_id, {"log": ["event1"]})
            evidence = await store.get_evidence(test_user_id)
            assert evidence["log"] == ["event1"]
