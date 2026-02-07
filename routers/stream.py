from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from core.event_bus import event_bus

router = APIRouter(tags=["Stream"])


@router.get("/events")
async def event_stream(request: Request) -> EventSourceResponse:
    """Server-Sent Events (SSE) endpoint.

    Clients connect here to receive real-time updates from the system.
    """
    queue: asyncio.Queue[dict[str, Any]] = await event_bus.subscribe()

    async def event_generator() -> AsyncGenerator[dict[str, str], None]:
        try:
            while True:
                if await request.is_disconnected():
                    break

                event: dict[str, Any] = await queue.get()
                yield {"event": "message", "data": json.dumps(event)}
        except asyncio.CancelledError:
            pass
        finally:
            event_bus.unsubscribe(queue)

    return EventSourceResponse(event_generator())
