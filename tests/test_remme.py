"""Tests for Phase 4b REMME stores and hubs -- mock asyncpg pool."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers: mock pool (same pattern as test_stores.py)
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
# MemoryStore
# ---------------------------------------------------------------------------


class TestMemoryStore:
    @pytest.mark.asyncio
    async def test_add(self) -> None:
        from core.stores.memory_store import MemoryStore

        pool = _mock_pool()
        embedding = np.zeros(768, dtype=np.float32)
        with patch("core.stores.memory_store.get_pool", AsyncMock(return_value=pool)):
            store = MemoryStore()
            memory_id = await store.add("u1", "test fact", "general", "manual", embedding)
            assert isinstance(memory_id, str)
            assert len(memory_id) > 0
            conn = pool.acquire().__aenter__.return_value
            assert conn.execute.called

    @pytest.mark.asyncio
    async def test_search_top_k(self) -> None:
        from core.stores.memory_store import MemoryStore

        rows = [
            {
                "id": "m1",
                "text": "fact 1",
                "category": "general",
                "source": "manual",
                "confidence": 1.0,
                "similarity": 0.95,
                "created_at": "2026-01-01",
                "metadata": {},
            },
            {
                "id": "m2",
                "text": "fact 2",
                "category": "general",
                "source": "manual",
                "confidence": 1.0,
                "similarity": 0.80,
                "created_at": "2026-01-01",
                "metadata": {},
            },
        ]
        pool = _mock_pool(fetch=rows)
        query_emb = np.zeros(768, dtype=np.float32)
        with patch("core.stores.memory_store.get_pool", AsyncMock(return_value=pool)):
            store = MemoryStore()
            results = await store.search("u1", query_emb, limit=5)
            assert len(results) == 2
            assert results[0]["id"] == "m1"

    @pytest.mark.asyncio
    async def test_search_with_min_similarity(self) -> None:
        from core.stores.memory_store import MemoryStore

        rows = [
            {
                "id": "m1",
                "text": "fact 1",
                "category": "general",
                "source": "manual",
                "confidence": 1.0,
                "similarity": 0.95,
                "created_at": "2026-01-01",
                "metadata": {},
            },
        ]
        pool = _mock_pool(fetch=rows)
        query_emb = np.zeros(768, dtype=np.float32)
        with patch("core.stores.memory_store.get_pool", AsyncMock(return_value=pool)):
            store = MemoryStore()
            results = await store.search("u1", query_emb, limit=5, min_similarity=0.8)
            assert len(results) == 1
            # Verify the SQL query included the min_similarity threshold
            conn = pool.acquire().__aenter__.return_value
            call_args = conn.fetch.call_args
            assert call_args is not None
            # The 4th positional arg should be the threshold
            assert call_args[0][4] == 0.8

    @pytest.mark.asyncio
    async def test_delete(self) -> None:
        from core.stores.memory_store import MemoryStore

        pool = _mock_pool(execute="DELETE 1")
        with patch("core.stores.memory_store.get_pool", AsyncMock(return_value=pool)):
            store = MemoryStore()
            result = await store.delete("u1", "m1")
            assert result is True

    @pytest.mark.asyncio
    async def test_delete_not_found(self) -> None:
        from core.stores.memory_store import MemoryStore

        pool = _mock_pool(execute="DELETE 0")
        with patch("core.stores.memory_store.get_pool", AsyncMock(return_value=pool)):
            store = MemoryStore()
            result = await store.delete("u1", "m-nonexistent")
            assert result is False

    @pytest.mark.asyncio
    async def test_get_all(self) -> None:
        from core.stores.memory_store import MemoryStore

        rows = [
            {
                "id": "m1",
                "text": "fact 1",
                "category": "general",
                "source": "manual",
                "confidence": 1.0,
                "created_at": "2026-01-02",
                "updated_at": "2026-01-02",
                "metadata": {},
            },
            {
                "id": "m2",
                "text": "fact 2",
                "category": "personal",
                "source": "scan",
                "confidence": 0.9,
                "created_at": "2026-01-01",
                "updated_at": "2026-01-01",
                "metadata": {},
            },
        ]
        pool = _mock_pool(fetch=rows)
        with patch("core.stores.memory_store.get_pool", AsyncMock(return_value=pool)):
            store = MemoryStore()
            results = await store.get_all("u1")
            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_update_text(self) -> None:
        from core.stores.memory_store import MemoryStore

        pool = _mock_pool(execute="UPDATE 1")
        new_emb = np.ones(768, dtype=np.float32)
        with patch("core.stores.memory_store.get_pool", AsyncMock(return_value=pool)):
            store = MemoryStore()
            result = await store.update_text("u1", "m1", "updated fact", new_emb)
            assert result is True

    @pytest.mark.asyncio
    async def test_update_text_not_found(self) -> None:
        from core.stores.memory_store import MemoryStore

        pool = _mock_pool(execute="UPDATE 0")
        new_emb = np.ones(768, dtype=np.float32)
        with patch("core.stores.memory_store.get_pool", AsyncMock(return_value=pool)):
            store = MemoryStore()
            result = await store.update_text("u1", "m-gone", "updated fact", new_emb)
            assert result is False


# ---------------------------------------------------------------------------
# PreferencesStore
# ---------------------------------------------------------------------------


class TestPreferencesStore:
    @pytest.mark.asyncio
    async def test_get_hub_data_empty(self) -> None:
        from core.stores.preferences_store import PreferencesStore

        pool = _mock_pool(fetchval=None)
        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=pool)):
            store = PreferencesStore()
            result = await store.get_hub_data("u1", "preferences")
            assert result == {}

    @pytest.mark.asyncio
    async def test_get_hub_data_existing(self) -> None:
        from core.stores.preferences_store import PreferencesStore

        data = {"theme": "dark", "lang": "en"}
        pool = _mock_pool(fetchval=json.dumps(data))
        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=pool)):
            store = PreferencesStore()
            result = await store.get_hub_data("u1", "preferences")
            assert result == data

    @pytest.mark.asyncio
    async def test_merge_hub_data(self) -> None:
        from core.stores.preferences_store import PreferencesStore

        pool = _mock_pool()
        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=pool)):
            store = PreferencesStore()
            await store.merge_hub_data("u1", "preferences", {"theme": "light"})
            conn = pool.acquire().__aenter__.return_value
            assert conn.execute.called

    @pytest.mark.asyncio
    async def test_save_hub_data_optimistic_lock_conflict(self) -> None:
        from core.stores.preferences_store import PreferencesStore

        # Simulate optimistic lock failure (no rows updated)
        pool = _mock_pool(execute="UPDATE 0")
        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=pool)):
            store = PreferencesStore()
            # Patch _ensure_row to be a no-op
            store._ensure_row = AsyncMock()  # type: ignore[method-assign]
            result = await store.save_hub_data("u1", "preferences", {"x": 1}, expected_updated_at="old-ts")
            assert result is False

    @pytest.mark.asyncio
    async def test_save_hub_data_success(self) -> None:
        from core.stores.preferences_store import PreferencesStore

        pool = _mock_pool(execute="UPDATE 1")
        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=pool)):
            store = PreferencesStore()
            store._ensure_row = AsyncMock()  # type: ignore[method-assign]
            result = await store.save_hub_data("u1", "preferences", {"x": 1}, expected_updated_at="some-ts")
            assert result is True

    @pytest.mark.asyncio
    async def test_invalid_hub_name(self) -> None:
        from core.stores.preferences_store import PreferencesStore

        store = PreferencesStore()
        with pytest.raises(ValueError, match="Unknown hub name"):
            await store.get_hub_data("u1", "nonexistent_hub")

    @pytest.mark.asyncio
    async def test_convenience_staging(self) -> None:
        from core.stores.preferences_store import PreferencesStore

        data = {"items": [{"key": "val"}]}
        pool = _mock_pool(fetchval=json.dumps(data))
        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=pool)):
            store = PreferencesStore()
            result = await store.get_staging("u1")
            assert result == data

    @pytest.mark.asyncio
    async def test_convenience_evidence(self) -> None:
        from core.stores.preferences_store import PreferencesStore

        data: dict[str, list[str]] = {"events": []}
        pool = _mock_pool(fetchval=json.dumps(data))
        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=pool)):
            store = PreferencesStore()
            result = await store.get_evidence("u1")
            assert result == data


# ---------------------------------------------------------------------------
# BaseHub
# ---------------------------------------------------------------------------


class TestBaseHub:
    @pytest.mark.asyncio
    async def test_load_and_access(self) -> None:
        from remme.hubs.base_hub import BaseHub

        pool = _mock_pool(fetchval=json.dumps({"theme": "dark"}))
        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=pool)):
            hub = BaseHub("preferences")
            await hub.load("u1")
            assert hub.data == {"theme": "dark"}
            assert hub.get("theme") == "dark"
            assert hub.get("missing", "default") == "default"

    def test_data_without_load_raises(self) -> None:
        from remme.hubs.base_hub import BaseHub

        hub = BaseHub("preferences")
        with pytest.raises(RuntimeError, match="not loaded"):
            _ = hub.data

    @pytest.mark.asyncio
    async def test_update_and_commit(self) -> None:
        from remme.hubs.base_hub import BaseHub

        pool = _mock_pool(fetchval=json.dumps({"a": 1}))
        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=pool)):
            hub = BaseHub("preferences")
            await hub.load("u1")
            hub.update("b", 2)
            assert hub.get("b") == 2
            await hub.commit("u1")
            conn = pool.acquire().__aenter__.return_value
            assert conn.execute.called

    @pytest.mark.asyncio
    async def test_commit_partial(self) -> None:
        from remme.hubs.base_hub import BaseHub

        pool = _mock_pool(fetchval=json.dumps({"a": 1, "b": 2, "c": 3}))
        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=pool)):
            hub = BaseHub("preferences")
            await hub.load("u1")
            hub.update("b", 99)
            await hub.commit_partial("u1", ["b"])
            conn = pool.acquire().__aenter__.return_value
            # Verify execute was called with partial data
            call_args = conn.execute.call_args
            assert call_args is not None
            # Args: (sql, user_id, json_data) — json_data is at index 2
            json_arg = call_args[0][2]
            parsed = json.loads(json_arg)
            assert parsed == {"b": 99}


# ---------------------------------------------------------------------------
# StagingQueue
# ---------------------------------------------------------------------------


class TestStagingQueue:
    @pytest.mark.asyncio
    async def test_load_and_count(self) -> None:
        from remme.staging import StagingQueue

        pool = _mock_pool(fetchval=json.dumps({"items": [{"k": "v"}]}))
        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=pool)):
            sq = StagingQueue()
            await sq.load("u1")
            assert sq.count == 1
            assert sq.items == [{"k": "v"}]

    def test_add_and_pop_all(self) -> None:
        from remme.staging import StagingQueue

        sq = StagingQueue()
        sq._queue = []
        sq.add({"item": 1})
        sq.add({"item": 2})
        assert sq.count == 2
        items = sq.pop_all()
        assert len(items) == 2
        assert sq.count == 0


# ---------------------------------------------------------------------------
# EvidenceLog
# ---------------------------------------------------------------------------


class TestEvidenceLog:
    @pytest.mark.asyncio
    async def test_load_and_add_event(self) -> None:
        from remme.engines.evidence_log import EvidenceLog

        pool = _mock_pool(fetchval=json.dumps({"events": []}))
        with patch("core.stores.preferences_store.get_pool", AsyncMock(return_value=pool)):
            log = EvidenceLog()
            await log.load("u1")
            event_id = log.add_event("session_scan", "some excerpt", session_id="s1")
            assert isinstance(event_id, str)
            assert len(log.events) == 1
            assert log.events[0]["source_type"] == "session_scan"
