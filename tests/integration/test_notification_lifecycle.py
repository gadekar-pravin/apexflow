"""Notification lifecycle tests -- CRUD, mark_read, unread_only filter, pagination.

Tests NotificationStore's create, list, mark_read, delete, and unread_only filtering.
Requires a real database. Tests are skipped when DB is unavailable.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
class TestNotificationLifecycle:
    """Verify NotificationStore CRUD and filtering behavior."""

    async def test_create_and_list_roundtrip(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Create notifications and list them."""
        from core.stores.notification_store import NotificationStore

        with patch("core.stores.notification_store.get_pool", AsyncMock(return_value=db_pool)):
            store = NotificationStore()
            nid = await store.create(test_user_id, source="scheduler", title="Job Done", body="Your job completed.")
            assert nid  # UUID string

            notifs = await store.list(test_user_id)
            assert len(notifs) == 1
            assert notifs[0]["title"] == "Job Done"
            assert notifs[0]["is_read"] is False

    async def test_mark_read(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """mark_read sets is_read to True."""
        from core.stores.notification_store import NotificationStore

        with patch("core.stores.notification_store.get_pool", AsyncMock(return_value=db_pool)):
            store = NotificationStore()
            nid = await store.create(test_user_id, source="test", title="Read Me", body="body")
            assert await store.mark_read(test_user_id, nid) is True

            notifs = await store.list(test_user_id)
            assert notifs[0]["is_read"] is True

    async def test_mark_read_nonexistent_returns_false(
        self, db_pool: Any, clean_tables: None, test_user_id: str
    ) -> None:
        """mark_read returns False for nonexistent notification."""
        from core.stores.notification_store import NotificationStore

        with patch("core.stores.notification_store.get_pool", AsyncMock(return_value=db_pool)):
            store = NotificationStore()
            assert await store.mark_read(test_user_id, "nonexistent") is False

    async def test_unread_only_filter(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """unread_only=True excludes read notifications."""
        from core.stores.notification_store import NotificationStore

        with patch("core.stores.notification_store.get_pool", AsyncMock(return_value=db_pool)):
            store = NotificationStore()
            nid_read = await store.create(test_user_id, source="test", title="Read", body="body")
            await store.create(test_user_id, source="test", title="Unread", body="body")
            await store.mark_read(test_user_id, nid_read)

            unread = await store.list(test_user_id, unread_only=True)
            assert len(unread) == 1
            assert unread[0]["title"] == "Unread"

            all_notifs = await store.list(test_user_id, unread_only=False)
            assert len(all_notifs) == 2

    async def test_pagination(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """list supports limit/offset pagination."""
        from core.stores.notification_store import NotificationStore

        with patch("core.stores.notification_store.get_pool", AsyncMock(return_value=db_pool)):
            store = NotificationStore()
            for i in range(5):
                await store.create(test_user_id, source="test", title=f"Notif {i}", body="body")

            page1 = await store.list(test_user_id, limit=2, offset=0)
            assert len(page1) == 2

            page2 = await store.list(test_user_id, limit=2, offset=2)
            assert len(page2) == 2

            page3 = await store.list(test_user_id, limit=2, offset=4)
            assert len(page3) == 1

    async def test_delete(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """delete returns True and removes the notification."""
        from core.stores.notification_store import NotificationStore

        with patch("core.stores.notification_store.get_pool", AsyncMock(return_value=db_pool)):
            store = NotificationStore()
            nid = await store.create(test_user_id, source="test", title="Delete Me", body="body")
            assert await store.delete(test_user_id, nid) is True
            assert await store.delete(test_user_id, nid) is False

            notifs = await store.list(test_user_id)
            assert len(notifs) == 0

    async def test_priority_and_metadata(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Priority and metadata JSONB fields are persisted."""
        from core.stores.notification_store import NotificationStore

        with patch("core.stores.notification_store.get_pool", AsyncMock(return_value=db_pool)):
            store = NotificationStore()
            await store.create(
                test_user_id,
                source="scheduler",
                title="Urgent",
                body="High priority notification",
                priority=5,
                metadata={"job_id": "j-123", "tags": ["important"]},
            )

            notifs = await store.list(test_user_id)
            assert len(notifs) == 1
            assert notifs[0]["priority"] == 5
            raw = notifs[0]["metadata"]
            meta = json.loads(raw) if isinstance(raw, str) else raw
            assert meta["job_id"] == "j-123"
            assert meta["tags"] == ["important"]
