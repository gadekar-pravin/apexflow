"""RAG router -- stub endpoints for Phase 3 (flat document list, option B).

Delegates to rag_service which raises NotImplementedError for all ops.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.auth import get_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rag", tags=["RAG"])


class SearchRequest(BaseModel):
    query: str
    limit: int = 5


class IndexRequest(BaseModel):
    filepath: str
    doc_type: str | None = None


@router.get("/documents")
async def list_documents(
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    return {
        "status": "stub",
        "message": "RAG document listing not yet implemented (Phase 4a)",
        "documents": [],
    }


@router.post("/search")
async def search_documents(
    request: SearchRequest,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    return {
        "status": "stub",
        "message": "RAG search not yet implemented (Phase 4a)",
        "results": [],
    }


@router.post("/index")
async def index_document(
    request: IndexRequest,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    return {
        "status": "stub",
        "message": "RAG indexing not yet implemented (Phase 4a)",
    }


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    return {
        "status": "stub",
        "message": "RAG deletion not yet implemented (Phase 4a)",
    }
