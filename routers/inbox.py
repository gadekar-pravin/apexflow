"""Inbox router -- v2 port from v1, DB-backed via NotificationStore.

Replaces SQLite (data/inbox/notifications.db) with AlloyDB notifications table.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth import get_user_id
from core.stores.notification_store import NotificationStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/inbox", tags=["Inbox"])

_notification_store = NotificationStore()


# -- models -------------------------------------------------------------------


class CreateNotificationRequest(BaseModel):
    source: str
    title: str
    body: str
    priority: int = 1
    metadata: dict[str, Any] | None = None


# -- convenience function (for scheduler / internal use) ----------------------


async def send_to_inbox(
    user_id: str,
    *,
    source: str,
    title: str,
    body: str,
    priority: int = 1,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Internal async API to send a notification to the inbox."""
    return await _notification_store.create(
        user_id,
        source=source,
        title=title,
        body=body,
        priority=priority,
        metadata=metadata,
    )


# -- endpoints ----------------------------------------------------------------


@router.get("")
async def get_notifications(
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    notifications = await _notification_store.list(user_id, unread_only=unread_only, limit=limit, offset=offset)
    return {"status": "success", "notifications": notifications}


@router.post("")
async def create_notification(
    request: CreateNotificationRequest,
    user_id: str = Depends(get_user_id),
) -> dict[str, str]:
    notif_id = await _notification_store.create(
        user_id,
        source=request.source,
        title=request.title,
        body=request.body,
        priority=request.priority,
        metadata=request.metadata,
    )
    return {"id": notif_id, "status": "created"}


@router.patch("/{notif_id}/read")
async def mark_as_read(
    notif_id: str,
    user_id: str = Depends(get_user_id),
) -> dict[str, str]:
    found = await _notification_store.mark_read(user_id, notif_id)
    if not found:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "updated"}


@router.delete("/{notif_id}")
async def delete_notification(
    notif_id: str,
    user_id: str = Depends(get_user_id),
) -> dict[str, str]:
    found = await _notification_store.delete(user_id, notif_id)
    if not found:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "deleted"}
