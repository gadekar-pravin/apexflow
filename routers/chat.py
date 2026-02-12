"""Chat router -- v2 port from v1, DB-backed via ChatStore.

Replaces filesystem (hashlib/pathlib) with chat_store queries.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth import get_user_id
from core.stores.chat_store import ChatStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["Chat"])

_chat_store = ChatStore()


# -- models -------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    target_type: str
    target_id: str
    title: str = "New Chat"
    model: str | None = None


class AddMessageRequest(BaseModel):
    role: str
    content: str
    metadata: dict[str, Any] | None = None


# -- endpoints ----------------------------------------------------------------


@router.get("/sessions")
async def list_chat_sessions(
    target_type: str | None = None,
    target_id: str | None = None,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    sessions = await _chat_store.list_sessions(user_id, target_type, target_id)
    return {"status": "success", "sessions": sessions}


@router.get("/sessions/{session_id}")
async def get_chat_session(
    session_id: str,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    session = await _chat_store.get_session(user_id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await _chat_store.get_messages(user_id, session_id)
    return {"status": "success", "session": session, "messages": messages}


@router.post("/sessions")
async def create_chat_session(
    request: CreateSessionRequest,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    session = await _chat_store.create_session(
        user_id,
        request.target_type,
        request.target_id,
        title=request.title,
        model=request.model,
    )
    return {"status": "success", "session": session}


@router.delete("/sessions/{session_id}")
async def delete_chat_session(
    session_id: str,
    user_id: str = Depends(get_user_id),
) -> dict[str, str]:
    await _chat_store.delete_session(user_id, session_id)
    return {"status": "success"}


@router.post("/sessions/{session_id}/messages")
async def add_message(
    session_id: str,
    request: AddMessageRequest,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    # Verify session exists
    session = await _chat_store.get_session(user_id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if request.metadata and len(json.dumps(request.metadata)) > 100_000:
        raise HTTPException(status_code=400, detail="Metadata too large (max 100KB)")

    msg = await _chat_store.add_message(
        user_id,
        session_id,
        request.role,
        request.content,
        metadata=request.metadata,
    )
    return {"status": "success", "message": msg}


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: str,
    limit: int = 100,
    offset: int = 0,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    messages = await _chat_store.get_messages(user_id, session_id, limit=limit, offset=offset)
    return {"status": "success", "messages": messages}
