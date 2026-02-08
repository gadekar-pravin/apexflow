"""RAG router -- document indexing, search, and management endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.auth import get_user_id
from core.rag.ingestion import embed_query, ingest_document, prepare_chunks
from core.stores.document_search import DocumentSearch
from core.stores.document_store import DocumentStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rag", tags=["RAG"])

_doc_store = DocumentStore()
_doc_search = DocumentSearch()


# -- request / response models -----------------------------------------------


class IndexRequest(BaseModel):
    filename: str
    content: str
    doc_type: str | None = None
    chunk_method: str = "rule_based"
    metadata: dict[str, Any] | None = None


class SearchRequest(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=50)


_REINDEX_MAX_BATCH = 50


class ReindexRequest(BaseModel):
    doc_id: str | None = None
    limit: int = Field(default=20, ge=1, le=_REINDEX_MAX_BATCH)


# -- endpoints ----------------------------------------------------------------


@router.get("/documents")
async def list_documents(
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    docs = await _doc_store.list_documents(user_id)
    return {"documents": docs}


@router.post("/search")
async def search_documents(
    request: SearchRequest,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    query_emb = await embed_query(request.query)
    results = await _doc_search.hybrid_search(
        user_id,
        request.query,
        query_emb,
        limit=request.limit,
    )
    return {"results": results}


@router.post("/index")
async def index_document(
    request: IndexRequest,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="Content must not be empty")
    result = await ingest_document(
        user_id,
        request.filename,
        request.content,
        doc_type=request.doc_type,
        chunk_method=request.chunk_method,
        metadata=request.metadata,
    )
    return result


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    deleted = await _doc_store.delete(user_id, doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": True, "doc_id": doc_id}


@router.post("/reindex")
async def reindex_documents(
    request: ReindexRequest,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    """Reindex a specific document or all stale documents."""
    if request.doc_id:
        doc = await _doc_store.get(user_id, request.doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        content = doc.get("content", "")
        if not content:
            raise HTTPException(status_code=400, detail="Document has no stored content")
        chunks, embeddings = await prepare_chunks(content)
        result = await _doc_store.reindex_document(user_id, request.doc_id, chunks, embeddings)
        return {"reindexed": [result]}

    # Reindex stale documents (content included, no extra query per doc)
    stale = await _doc_store.list_stale_documents(user_id, limit=request.limit)
    results = []
    for doc in stale:
        content = doc.get("content", "")
        if not content:
            continue
        chunks, embeddings = await prepare_chunks(content)
        result = await _doc_store.reindex_document(user_id, doc["id"], chunks, embeddings)
        results.append(result)

    return {"reindexed": results}
