"""RemmeStore -- facade wrapping MemoryStore + PreferencesStore + SessionStore."""

from __future__ import annotations

import logging
from typing import Any

from core.stores.memory_store import MemoryStore
from core.stores.preferences_store import PreferencesStore
from core.stores.session_store import SessionStore
from remme.utils import get_embedding

logger = logging.getLogger(__name__)

_memory_store = MemoryStore()
_preferences_store = PreferencesStore()
_session_store = SessionStore()


class RemmeStore:
    """High-level facade for REMME memory operations.

    Auto-generates embeddings via ``remme.utils.get_embedding`` before
    delegating to ``MemoryStore``.
    """

    async def add(
        self,
        user_id: str,
        text: str,
        *,
        category: str = "general",
        source: str = "manual",
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add a memory, auto-embedding the text."""
        embedding = get_embedding(text, "RETRIEVAL_DOCUMENT")
        return await _memory_store.add(
            user_id,
            text,
            category,
            source,
            embedding,
            confidence,
            metadata=metadata,
        )

    async def search(
        self,
        user_id: str,
        query: str,
        *,
        limit: int = 10,
        min_similarity: float | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search over memories."""
        query_embedding = get_embedding(query, "RETRIEVAL_QUERY")
        return await _memory_store.search(
            user_id,
            query_embedding,
            limit=limit,
            min_similarity=min_similarity,
        )

    async def list_all(self, user_id: str) -> list[dict[str, Any]]:
        """Return all memories for a user."""
        return await _memory_store.get_all(user_id)

    async def delete(self, user_id: str, memory_id: str) -> bool:
        """Delete a memory by ID."""
        return await _memory_store.delete(user_id, memory_id)

    async def update_text(self, user_id: str, memory_id: str, new_text: str) -> bool:
        """Update a memory's text, auto-re-embedding."""
        new_embedding = get_embedding(new_text, "RETRIEVAL_DOCUMENT")
        return await _memory_store.update_text(user_id, memory_id, new_text, new_embedding)

    async def get_profile(self, user_id: str) -> dict[str, Any]:
        """Build a basic profile summary from memory count + preferences."""
        memories = await _memory_store.get_all(user_id)
        prefs = await _preferences_store.get_hub_data(user_id, "preferences")
        return {
            "memory_count": len(memories),
            "preferences": prefs,
        }

    async def get_preferences(self, user_id: str) -> dict[str, Any]:
        """Return the user's preferences hub data."""
        return await _preferences_store.get_hub_data(user_id, "preferences")

    async def list_unscanned(self, user_id: str) -> list[dict[str, Any]]:
        """List sessions not yet scanned by REMME."""
        return await _session_store.list_unscanned(user_id)

    async def mark_scanned(self, user_id: str, session_id: str) -> None:
        """Mark a session as scanned (delegates to SessionStore)."""
        await _session_store.mark_scanned(user_id, session_id)
