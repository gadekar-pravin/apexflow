"""Evidence log -- event log backed by PreferencesStore."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from core.stores.preferences_store import PreferencesStore

logger = logging.getLogger(__name__)

_preferences_store = PreferencesStore()


class EvidenceLog:
    """In-memory evidence event log with async DB load/save."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []

    async def load(self, user_id: str) -> None:
        """Load evidence log from DB."""
        data = await _preferences_store.get_evidence(user_id)
        self._events = data.get("events", [])

    async def save(self, user_id: str) -> None:
        """Persist evidence log to DB."""
        await _preferences_store.save_evidence(user_id, {"events": self._events})

    def add_event(
        self,
        source_type: str,
        raw_excerpt: str,
        *,
        session_id: str | None = None,
        category: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add an evidence event and return its ID."""
        event_id = str(uuid.uuid4())
        self._events.append(
            {
                "id": event_id,
                "source_type": source_type,
                "raw_excerpt": raw_excerpt,
                "session_id": session_id,
                "category": category,
                "metadata": metadata or {},
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        return event_id

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)
