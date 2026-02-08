"""Staging queue -- in-memory queue backed by PreferencesStore."""

from __future__ import annotations

import logging
from typing import Any

from core.stores.preferences_store import PreferencesStore

logger = logging.getLogger(__name__)

_preferences_store = PreferencesStore()


class StagingQueue:
    """In-memory staging queue with async DB load/save."""

    def __init__(self) -> None:
        self._queue: list[dict[str, Any]] = []

    async def load(self, user_id: str) -> None:
        """Load staging queue from DB."""
        data = await _preferences_store.get_staging(user_id)
        self._queue = data.get("items", [])

    async def save(self, user_id: str) -> None:
        """Persist staging queue to DB."""
        await _preferences_store.save_staging(user_id, {"items": self._queue})

    def add(self, item: dict[str, Any]) -> None:
        """Add an item to the staging queue."""
        self._queue.append(item)

    def pop_all(self) -> list[dict[str, Any]]:
        """Remove and return all items."""
        items = list(self._queue)
        self._queue.clear()
        return items

    @property
    def count(self) -> int:
        return len(self._queue)

    @property
    def items(self) -> list[dict[str, Any]]:
        return list(self._queue)
