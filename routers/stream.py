from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from core.event_bus import event_bus

router = APIRouter(tags=["Stream"])

# Keep-alive interval (seconds). Cloud Run and Firebase Hosting proxies
# terminate idle streaming connections, so we send periodic pings.
PING_INTERVAL = 15


@router.get("/events")
async def event_stream(request: Request) -> EventSourceResponse:
    """Server-Sent Events (SSE) endpoint.

    Clients connect here to receive real-time updates from the system.
    Uses sse-starlette's built-in ping to keep the connection alive
    through Cloud Run and Firebase Hosting proxies.
    """
    queue: asyncio.Queue[dict[str, Any]] = await event_bus.subscribe()

    async def event_generator() -> AsyncGenerator[dict[str, str], None]:
        try:
            # Flush response headers immediately so EventSource.onopen fires
            yield {"comment": "connected"}

            while True:
                try:
                    event: dict[str, Any] = await asyncio.wait_for(queue.get(), timeout=PING_INTERVAL)
                    yield {"event": "message", "data": json.dumps(event)}
                except TimeoutError:
                    yield {"comment": "ping"}
        except asyncio.CancelledError:
            pass
        finally:
            event_bus.unsubscribe(queue)

    return EventSourceResponse(
        event_generator(),
    )
