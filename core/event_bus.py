from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("event_bus")


class EventBus:
    _instance: EventBus | None = None
    _subscribers: list[asyncio.Queue[dict[str, Any]]]
    _history: deque[dict[str, Any]]

    def __new__(cls) -> EventBus:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._subscribers = []
            cls._instance._history = deque(maxlen=100)
        return cls._instance

    async def publish(self, event_type: str, source: str, data: dict[str, Any]) -> None:
        """Publish an event to all subscribers."""
        event = {"timestamp": datetime.now(UTC).isoformat(), "type": event_type, "source": source, "data": data}

        self._history.append(event)
        logger.debug("Event: %s from %s", event_type, source)

        for q in list(self._subscribers):
            try:
                await q.put(event)
            except Exception as e:
                logger.error("Failed to push to subscriber: %s", e)

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """Subscribe to the event stream."""
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.append(q)

        for event in list(self._history)[-5:]:
            await q.put(event)

        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)


# Global Instance
event_bus = EventBus()
