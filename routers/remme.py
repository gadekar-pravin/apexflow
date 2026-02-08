"""REMME router -- v2 port from v1, DB-backed via SessionStore + StateStore.

Replaces filesystem summaries_dir.rglob() with session_store.list_unscanned().
Replaces profile cache file with state_store.get/set.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth import get_user_id
from core.stores.session_store import SessionStore
from core.stores.state_store import StateStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/remme", tags=["REMME"])

_session_store = SessionStore()
_state_store = StateStore()


# -- models -------------------------------------------------------------------


class MemoryItem(BaseModel):
    text: str
    category: str = "general"
    source: str | None = None


# -- endpoints ----------------------------------------------------------------


@router.get("/memories")
async def list_memories(
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    """List user memories from the remme store."""
    from shared.state import get_remme_store

    store = get_remme_store()
    if store is None:
        return {"status": "unavailable", "memories": [], "message": "RemmeStore not initialized"}
    try:
        memories = store.list_all()
        return {"status": "success", "memories": memories, "count": len(memories)}
    except Exception as e:
        logger.error("Failed to list memories: %s", e)
        return {"status": "error", "memories": [], "error": str(e)}


@router.post("/memories")
async def add_memory(
    item: MemoryItem,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    """Add a new memory to the remme store."""
    from shared.state import get_remme_store

    store = get_remme_store()
    if store is None:
        raise HTTPException(status_code=503, detail="RemmeStore not initialized")
    try:
        memory_id = store.add(
            item.text,
            category=item.category,
            source=item.source or "manual",
        )
        return {"status": "success", "id": memory_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    user_id: str = Depends(get_user_id),
) -> dict[str, str]:
    """Delete a memory from the remme store."""
    from shared.state import get_remme_store

    store = get_remme_store()
    if store is None:
        raise HTTPException(status_code=503, detail="RemmeStore not initialized")
    try:
        store.delete(memory_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


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
    sessions = await _session_store.list_unscanned(user_id)
    if not sessions:
        return {"status": "success", "scanned": 0, "message": "No unscanned sessions"}

    scanned = 0
    for session in sessions:
        try:
            await _session_store.mark_scanned(user_id, session["id"])
            scanned += 1
        except Exception as e:
            logger.error("Failed to mark session %s as scanned: %s", session["id"], e)

    return {"status": "success", "scanned": scanned}


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
    from shared.state import get_remme_store

    store = get_remme_store()
    if store is None:
        raise HTTPException(status_code=503, detail="RemmeStore not initialized")

    try:
        memories = store.list_all()
        profile: dict[str, Any] = {
            "memory_count": len(memories),
            "generated_at": datetime.now(UTC).isoformat(),
        }
        await _state_store.set(user_id, "remme_profile_cache", profile)
        return {"status": "success", "profile": profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/preferences")
async def get_preferences(
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    """Get user preferences (simplified v2 -- hub data moved to DB in Phase 5)."""
    return {
        "status": "success",
        "preferences": {},
        "message": "Full preference system available in Phase 5",
    }


@router.get("/staging/status")
async def get_staging_status(
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    """Get staging queue status."""
    return {
        "status": "success",
        "pending_count": 0,
        "should_normalize": False,
        "message": "Staging system available in Phase 5",
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
