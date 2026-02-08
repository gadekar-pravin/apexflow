"""REMME router -- DB-backed via RemmeStore + RemmeEngine (Phase 4b).

Replaces Phase 3 stubs with real store/engine calls.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.auth import get_user_id
from core.stores.preferences_store import PreferencesStore
from core.stores.session_store import SessionStore
from core.stores.state_store import StateStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/remme", tags=["REMME"])

_session_store = SessionStore()
_state_store = StateStore()
_preferences_store = PreferencesStore()


# -- models -------------------------------------------------------------------


class MemoryItem(BaseModel):
    text: str
    category: str = "general"
    source: str | None = None


class SearchQuery(BaseModel):
    query: str
    limit: int = Field(default=10, ge=1, le=100)


# -- helpers ------------------------------------------------------------------


def _get_store() -> Any:
    from shared.state import get_remme_store

    store = get_remme_store()
    if store is None:
        raise HTTPException(status_code=503, detail="RemmeStore not initialized")
    return store


# -- endpoints ----------------------------------------------------------------


@router.get("/memories")
async def list_memories(
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    """List user memories from the remme store."""
    store = _get_store()
    memories = await store.list_all(user_id)
    return {"status": "success", "memories": memories, "count": len(memories)}


@router.post("/memories")
async def add_memory(
    item: MemoryItem,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    """Add a new memory to the remme store."""
    store = _get_store()
    memory_id = await store.add(
        user_id,
        item.text,
        category=item.category,
        source=item.source or "manual",
    )
    return {"status": "success", "id": memory_id}


@router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    """Delete a memory from the remme store."""
    store = _get_store()
    deleted = await store.delete(user_id, memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"status": "success"}


@router.post("/memories/search")
async def search_memories(
    body: SearchQuery,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    """Semantic search over memories."""
    store = _get_store()
    results = await store.search(user_id, body.query, limit=body.limit)
    return {"status": "success", "results": results, "count": len(results)}


@router.get("/scan/unscanned")
async def list_unscanned(
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    """List sessions not yet scanned by REMME."""
    sessions = await _session_store.list_unscanned(user_id)
    return {"status": "success", "sessions": sessions, "count": len(sessions)}


@router.post("/scan/smart")
async def smart_scan(
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    """Scan unscanned sessions and extract memories."""
    store = _get_store()

    from remme.engine import RemmeEngine

    engine = RemmeEngine(store)
    result = await engine.run_scan(user_id)
    return {"status": "success", **result}


@router.get("/profile")
async def get_profile(
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    """Get cached user profile or return empty."""
    cached = await _state_store.get(user_id, "remme_profile_cache")
    if cached:
        return {"status": "success", "profile": cached}
    return {"status": "success", "profile": None, "message": "No profile cached yet"}


@router.post("/profile/refresh")
async def refresh_profile(
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    """Regenerate the user profile from memories."""
    store = _get_store()
    profile = await store.get_profile(user_id)
    profile["generated_at"] = datetime.now(UTC).isoformat()
    await _state_store.set(user_id, "remme_profile_cache", profile)
    return {"status": "success", "profile": profile}


@router.get("/preferences")
async def get_preferences(
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    """Get user preferences from the preferences store."""
    store = _get_store()
    preferences = await store.get_preferences(user_id)
    return {"status": "success", "preferences": preferences}


@router.get("/staging/status")
async def get_staging_status(
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    """Get staging queue status."""
    data = await _preferences_store.get_staging(user_id)
    items = data.get("items", [])
    return {
        "status": "success",
        "pending_count": len(items),
        "should_normalize": len(items) >= 5,
        "items": items,
    }


@router.post("/normalize")
async def run_normalize(
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    """Run normalizer (stub for Phase 5)."""
    return {
        "status": "stub",
        "message": "Normalizer available in Phase 5",
        "changes": [],
    }
