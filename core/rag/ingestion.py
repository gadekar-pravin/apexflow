"""RAG ingestion pipeline -- chunk, embed, store."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.rag.chunker import chunk_document
from core.stores.document_store import DocumentStore

logger = logging.getLogger(__name__)

_doc_store = DocumentStore()


async def ingest_document(
    user_id: str,
    filename: str,
    content: str,
    *,
    doc_type: str | None = None,
    chunk_method: str = "rule_based",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Orchestrate: chunk -> embed -> store.

    Returns the result dict from ``DocumentStore.index_document``.
    """
    chunks = await chunk_document(content, method=chunk_method)
    if not chunks:
        return {"doc_id": None, "status": "empty", "total_chunks": 0}

    embeddings = await _batch_embed(chunks)

    return await _doc_store.index_document(
        user_id,
        filename,
        content,
        chunks,
        embeddings,
        doc_type=doc_type,
        metadata=metadata,
    )


async def embed_query(query_text: str) -> Any:
    """Embed a search query (RETRIEVAL_QUERY task type)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_embed_query, query_text)


def _sync_embed_query(query_text: str) -> Any:
    from remme.utils import get_embedding

    return get_embedding(query_text, "RETRIEVAL_QUERY")


async def _batch_embed(texts: list[str]) -> list[Any]:
    """Embed multiple texts concurrently via thread pool."""
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, _sync_embed_doc, t) for t in texts]
    return list(await asyncio.gather(*tasks))


def _sync_embed_doc(text: str) -> Any:
    from remme.utils import get_embedding

    return get_embedding(text, "RETRIEVAL_DOCUMENT")
