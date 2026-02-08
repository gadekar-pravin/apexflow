"""Base hub -- async adapter for sync in-memory data with DB persistence."""

from __future__ import annotations

import logging
from typing import Any

from core.stores.preferences_store import PreferencesStore

logger = logging.getLogger(__name__)

_preferences_store = PreferencesStore()


class BaseHub:
    """Async adapter: sync in-memory data, async load/commit.

    Subclass or use directly for any hub backed by a ``user_preferences``
    JSONB column (preferences, operating_context, soft_identity, etc.).
    """

    def __init__(self, hub_name: str) -> None:
        self.hub_name = hub_name
        self._data: dict[str, Any] | None = None
        self._loaded = False

    async def load(self, user_id: str) -> None:
        """Load hub data from DB into memory."""
        self._data = await _preferences_store.get_hub_data(user_id, self.hub_name)
        self._loaded = True

    async def commit(self, user_id: str) -> None:
        """Write entire in-memory data back to DB via merge."""
        await _preferences_store.merge_hub_data(user_id, self.hub_name, self.data)

    async def commit_partial(self, user_id: str, keys: list[str]) -> None:
        """Write only specified keys back to DB."""
        partial = {k: self.data[k] for k in keys if k in self.data}
        if partial:
            await _preferences_store.merge_hub_data(user_id, self.hub_name, partial)

    @property
    def data(self) -> dict[str, Any]:
        """Sync access to in-memory data. Raises if not loaded."""
        if not self._loaded:
            raise RuntimeError(f"Hub {self.hub_name!r} not loaded — call load() first")
        assert self._data is not None
        return self._data

    def update(self, key: str, value: Any) -> None:
        """Sync update of an in-memory key."""
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Sync read of an in-memory key."""
        return self.data.get(key, default)
