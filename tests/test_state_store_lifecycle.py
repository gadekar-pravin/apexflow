"""State store lifecycle tests -- UPSERT semantics, composite PK, JSONB roundtrip.

Tests StateStore's INSERT ON CONFLICT DO UPDATE behavior, composite
primary key (user_id, key), and JSONB value roundtrip.
Requires a real database. Tests are skipped when DB is unavailable.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
class TestStateStoreLifecycle:
    """Verify StateStore UPSERT, delete, and JSONB handling."""

    async def test_set_and_get_roundtrip(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """set() then get() returns the same value."""
        from core.stores.state_store import StateStore

        with patch("core.stores.state_store.get_pool", AsyncMock(return_value=db_pool)):
            store = StateStore()
            await store.set(test_user_id, "config", {"theme": "dark", "version": 2})

            result = await store.get(test_user_id, "config")
            assert result == {"theme": "dark", "version": 2}

    async def test_upsert_overwrites_existing(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Second set() with same key overwrites the value."""
        from core.stores.state_store import StateStore

        with patch("core.stores.state_store.get_pool", AsyncMock(return_value=db_pool)):
            store = StateStore()
            await store.set(test_user_id, "counter", {"count": 1})
            await store.set(test_user_id, "counter", {"count": 2})

            result = await store.get(test_user_id, "counter")
            assert result == {"count": 2}

    async def test_different_keys_independent(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Different keys under the same user are independent."""
        from core.stores.state_store import StateStore

        with patch("core.stores.state_store.get_pool", AsyncMock(return_value=db_pool)):
            store = StateStore()
            await store.set(test_user_id, "key_a", {"a": 1})
            await store.set(test_user_id, "key_b", {"b": 2})

            assert await store.get(test_user_id, "key_a") == {"a": 1}
            assert await store.get(test_user_id, "key_b") == {"b": 2}

    async def test_get_nonexistent_returns_none(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """get() returns None for a nonexistent key."""
        from core.stores.state_store import StateStore

        with patch("core.stores.state_store.get_pool", AsyncMock(return_value=db_pool)):
            store = StateStore()
            assert await store.get(test_user_id, "does_not_exist") is None

    async def test_delete_returns_true_and_removes(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """delete() returns True and removes the entry."""
        from core.stores.state_store import StateStore

        with patch("core.stores.state_store.get_pool", AsyncMock(return_value=db_pool)):
            store = StateStore()
            await store.set(test_user_id, "temp", {"value": 42})
            assert await store.delete(test_user_id, "temp") is True
            assert await store.get(test_user_id, "temp") is None

    async def test_delete_nonexistent_returns_false(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """delete() returns False for a nonexistent key."""
        from core.stores.state_store import StateStore

        with patch("core.stores.state_store.get_pool", AsyncMock(return_value=db_pool)):
            store = StateStore()
            assert await store.delete(test_user_id, "nope") is False

    async def test_complex_jsonb_roundtrip(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Deeply nested JSONB values roundtrip correctly."""
        from core.stores.state_store import StateStore

        complex_value = {
            "metrics": {
                "daily": [{"date": "2025-01-01", "runs": 5, "cost": 0.05}],
                "totals": {"runs": 100, "cost": 1.5},
            },
            "flags": [True, False, None],
            "empty": {},
        }

        with patch("core.stores.state_store.get_pool", AsyncMock(return_value=db_pool)):
            store = StateStore()
            await store.set(test_user_id, "complex", complex_value)

            result = await store.get(test_user_id, "complex")
            assert result == complex_value
