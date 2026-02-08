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
    """Orchestrate: dedup check -> chunk -> embed -> store.

    Returns the result dict from ``DocumentStore.index_document``.
    """
    # Early dedup check — avoid expensive chunking/embedding when the
    # same content with identical settings is already indexed.
    dup = await _doc_store.is_duplicate(user_id, content, chunk_method)
    if dup:
        # Still persist any updated filename / doc_type / metadata.
        await _doc_store.update_document_metadata(
            user_id,
            dup["doc_id"],
            filename,
            doc_type=doc_type,
            metadata=metadata,
        )
        return dup

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
        chunk_method=chunk_method,
        doc_type=doc_type,
        metadata=metadata,
    )


async def prepare_chunks(content: str, *, method: str = "rule_based") -> tuple[list[str], list[Any]]:
    """Chunk text and embed all chunks.  Returns ``(chunks, embeddings)``.

    This is the public entry-point used by the reindex router so it does
    not need to import private helpers.
    """
    chunks = await chunk_document(content, method=method)
    if not chunks:
        return [], []
    embeddings = await _batch_embed(chunks)
    return chunks, embeddings


async def embed_query(query_text: str) -> Any:
    """Embed a search query (RETRIEVAL_QUERY task type)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync_embed_query, query_text)


def _sync_embed_query(query_text: str) -> Any:
    from remme.utils import get_embedding

    return get_embedding(query_text, "RETRIEVAL_QUERY")


async def _batch_embed(texts: list[str]) -> list[Any]:
    """Embed multiple texts concurrently via thread pool."""
    loop = asyncio.get_running_loop()
    tasks = [loop.run_in_executor(None, _sync_embed_doc, t) for t in texts]
    return list(await asyncio.gather(*tasks))


def _sync_embed_doc(text: str) -> Any:
    from remme.utils import get_embedding

    return get_embedding(text, "RETRIEVAL_DOCUMENT")
