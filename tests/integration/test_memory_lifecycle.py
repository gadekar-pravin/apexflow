"""Memory lifecycle tests -- vector search, min_similarity, update_text re-embedding.

Tests MemoryStore's cosine similarity search with min_similarity threshold,
update_text re-embedding, category filtering, and confidence field precision.
Requires a real database. Tests are skipped when DB is unavailable.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

_rng = np.random.default_rng(42)


def _make_embedding(base_idx: int, noise: float = 0.05) -> list[float]:
    """Create a synthetic 768-dim embedding centered on a base direction."""
    vec = _rng.random(768).astype(np.float32) * noise
    start = base_idx * 100
    vec[start : start + 100] = 1.0
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec = vec / norm
    return [float(x) for x in vec]


def _make_orthogonal_embedding(base_idx: int) -> list[float]:
    """Create a clean orthogonal embedding with no noise for predictable similarity."""
    vec = np.zeros(768, dtype=np.float32)
    start = base_idx * 100
    vec[start : start + 100] = 1.0
    norm = float(np.linalg.norm(vec))
    vec = vec / norm
    return [float(x) for x in vec]


@pytest.mark.asyncio
class TestMemoryLifecycle:
    """Verify MemoryStore CRUD, vector search, and update behavior."""

    async def test_add_and_get_all_roundtrip(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Add 3 memories, get_all returns newest first."""
        from core.stores.memory_store import MemoryStore

        with patch("core.stores.memory_store.get_pool", AsyncMock(return_value=db_pool)):
            store = MemoryStore()
            for i in range(3):
                await store.add(
                    test_user_id,
                    text=f"Memory {i}",
                    category="general",
                    source="test",
                    embedding=_make_embedding(i),
                )

            memories = await store.get_all(test_user_id)
            assert len(memories) == 3
            # Newest first
            assert memories[0]["text"] == "Memory 2"
            assert memories[2]["text"] == "Memory 0"

    async def test_search_returns_most_similar_first(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Orthogonal embeddings ensure the closest match ranks first."""
        from core.stores.memory_store import MemoryStore

        with patch("core.stores.memory_store.get_pool", AsyncMock(return_value=db_pool)):
            store = MemoryStore()
            await store.add(
                test_user_id,
                text="Python programming",
                category="tech",
                source="test",
                embedding=_make_orthogonal_embedding(0),
            )
            await store.add(
                test_user_id,
                text="Machine learning",
                category="tech",
                source="test",
                embedding=_make_orthogonal_embedding(1),
            )
            await store.add(
                test_user_id,
                text="Database design",
                category="tech",
                source="test",
                embedding=_make_orthogonal_embedding(2),
            )

            # Search with embedding close to base_idx=1 (machine learning)
            results = await store.search(test_user_id, _make_orthogonal_embedding(1), limit=3)
            assert len(results) == 3
            assert results[0]["text"] == "Machine learning"
            assert results[0]["similarity"] > 0.99

    async def test_search_min_similarity_filters_low_matches(
        self, db_pool: Any, clean_tables: None, test_user_id: str
    ) -> None:
        """min_similarity filters out low-similarity results."""
        from core.stores.memory_store import MemoryStore

        with patch("core.stores.memory_store.get_pool", AsyncMock(return_value=db_pool)):
            store = MemoryStore()
            await store.add(
                test_user_id,
                text="Close match",
                category="general",
                source="test",
                embedding=_make_orthogonal_embedding(0),
            )
            await store.add(
                test_user_id,
                text="Far away",
                category="general",
                source="test",
                embedding=_make_orthogonal_embedding(5),
            )

            # Query close to base_idx=0, high threshold
            results = await store.search(
                test_user_id,
                _make_orthogonal_embedding(0),
                limit=10,
                min_similarity=0.9,
            )
            # Only the close match should pass
            assert len(results) == 1
            assert results[0]["text"] == "Close match"

    async def test_search_limit_respected(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """search limit parameter caps the number of results."""
        from core.stores.memory_store import MemoryStore

        with patch("core.stores.memory_store.get_pool", AsyncMock(return_value=db_pool)):
            store = MemoryStore()
            for i in range(10):
                await store.add(
                    test_user_id,
                    text=f"Memory {i}",
                    category="general",
                    source="test",
                    embedding=_make_embedding(i % 7),
                )

            results = await store.search(test_user_id, _make_embedding(0), limit=3)
            assert len(results) == 3

    async def test_update_text_changes_text_and_embedding(
        self, db_pool: Any, clean_tables: None, test_user_id: str
    ) -> None:
        """update_text replaces text and re-embeds."""
        from core.stores.memory_store import MemoryStore

        with patch("core.stores.memory_store.get_pool", AsyncMock(return_value=db_pool)):
            store = MemoryStore()
            mem_id = await store.add(
                test_user_id,
                text="Original text",
                category="general",
                source="test",
                embedding=_make_orthogonal_embedding(0),
            )

            new_emb = _make_orthogonal_embedding(3)
            ok = await store.update_text(test_user_id, mem_id, "Updated text", new_emb)
            assert ok is True

            memories = await store.get_all(test_user_id)
            assert len(memories) == 1
            assert memories[0]["text"] == "Updated text"

            # Verify embedding changed by searching
            results = await store.search(test_user_id, _make_orthogonal_embedding(3), limit=1)
            assert results[0]["similarity"] > 0.99

    async def test_update_text_returns_false_for_nonexistent(
        self, db_pool: Any, clean_tables: None, test_user_id: str
    ) -> None:
        """update_text returns False for a nonexistent memory."""
        from core.stores.memory_store import MemoryStore

        with patch("core.stores.memory_store.get_pool", AsyncMock(return_value=db_pool)):
            store = MemoryStore()
            ok = await store.update_text(test_user_id, "nonexistent-id", "text", _make_embedding(0))
            assert ok is False

    async def test_delete_returns_true_and_removes(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """delete returns True and removes the memory."""
        from core.stores.memory_store import MemoryStore

        with patch("core.stores.memory_store.get_pool", AsyncMock(return_value=db_pool)):
            store = MemoryStore()
            mem_id = await store.add(
                test_user_id,
                text="Delete me",
                category="general",
                source="test",
                embedding=_make_embedding(0),
            )
            assert await store.delete(test_user_id, mem_id) is True
            memories = await store.get_all(test_user_id)
            assert len(memories) == 0

    async def test_delete_returns_false_for_nonexistent(
        self, db_pool: Any, clean_tables: None, test_user_id: str
    ) -> None:
        """delete returns False for a nonexistent memory."""
        from core.stores.memory_store import MemoryStore

        with patch("core.stores.memory_store.get_pool", AsyncMock(return_value=db_pool)):
            store = MemoryStore()
            assert await store.delete(test_user_id, "nonexistent-id") is False

    async def test_confidence_field_persisted(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """REAL type confidence field preserves precision."""
        from core.stores.memory_store import MemoryStore

        with patch("core.stores.memory_store.get_pool", AsyncMock(return_value=db_pool)):
            store = MemoryStore()
            await store.add(
                test_user_id,
                text="High confidence",
                category="fact",
                source="test",
                embedding=_make_embedding(0),
                confidence=0.875,
            )

            memories = await store.get_all(test_user_id)
            assert len(memories) == 1
            assert abs(memories[0]["confidence"] - 0.875) < 1e-6
