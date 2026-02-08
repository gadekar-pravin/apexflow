"""Document store -- CRUD for ``documents`` and ``document_chunks`` tables."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Any

import numpy as np

from core.database import get_pool
from core.rag.config import EMBEDDING_DIM, EMBEDDING_MODEL, INGESTION_VERSION

logger = logging.getLogger(__name__)


class DocumentStore:
    """Stateless data-access object for the documents + document_chunks tables."""

    # -- index (upsert) -------------------------------------------------------

    async def is_duplicate(
        self,
        user_id: str,
        content: str,
        chunk_method: str,
    ) -> dict[str, Any] | None:
        """Check if a document with identical content and settings exists.

        Returns a dedup result dict if the document is already indexed with
        the same hash, ingestion version, chunk method, and embedding config.
        Returns ``None`` if no match — caller should proceed with ingestion.
        """
        file_hash = hashlib.sha256(content.encode()).hexdigest()
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, total_chunks
                FROM documents
                WHERE user_id = $1
                  AND file_hash = $2
                  AND ingestion_version = $3
                  AND chunk_method = $4
                  AND embedding_model = $5
                  AND embedding_dim = $6
                """,
                user_id,
                file_hash,
                INGESTION_VERSION,
                chunk_method,
                EMBEDDING_MODEL,
                EMBEDDING_DIM,
            )
        if row:
            return {
                "doc_id": row["id"],
                "status": "deduplicated",
                "total_chunks": row["total_chunks"],
            }
        return None

    async def update_document_metadata(
        self,
        user_id: str,
        doc_id: str,
        filename: str,
        *,
        doc_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Update mutable fields on an existing document row."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE documents
                SET filename = $3,
                    doc_type = $4,
                    metadata = $5::jsonb,
                    updated_at = NOW()
                WHERE id = $1 AND user_id = $2
                """,
                doc_id,
                user_id,
                filename,
                doc_type,
                json.dumps(metadata or {}),
            )

    async def index_document(
        self,
        user_id: str,
        filename: str,
        content: str,
        chunks: list[str],
        embeddings: list[Any],
        *,
        chunk_method: str = "rule_based",
        doc_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Index a document with its chunks and embeddings.

        Uses content-hash dedup: same user + same hash + same ingestion version
        + same chunk method + same embedding config means the document is
        already indexed and can be skipped.

        Returns dict with ``doc_id``, ``status`` ("indexed" or "deduplicated"),
        and ``total_chunks``.
        """
        file_hash = hashlib.sha256(content.encode()).hexdigest()
        doc_id = str(uuid.uuid4())

        pool = await get_pool()
        async with pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO documents
                    (id, user_id, filename, doc_type, file_hash, content,
                     total_chunks, embedding_model, embedding_dim,
                     ingestion_version, chunk_method, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb)
                ON CONFLICT (user_id, file_hash) DO UPDATE
                    SET filename = EXCLUDED.filename,
                        doc_type = EXCLUDED.doc_type,
                        content = EXCLUDED.content,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                RETURNING id, (xmax = 0) AS is_new,
                          ingestion_version, chunk_method,
                          embedding_model, embedding_dim, total_chunks
                """,
                doc_id,
                user_id,
                filename,
                doc_type,
                file_hash,
                content,
                len(chunks),
                EMBEDDING_MODEL,
                EMBEDDING_DIM,
                INGESTION_VERSION,
                chunk_method,
                json.dumps(metadata or {}),
            )

            actual_id: str = row["id"]  # type: ignore[index]
            is_new: bool = row["is_new"]  # type: ignore[index]

            if not is_new:
                # Check if all settings match — if so, skip re-chunking.
                # Version/chunk/embedding fields are NOT updated in the
                # upsert above so the RETURNING values reflect the
                # *existing* row.
                if (
                    row["ingestion_version"] == INGESTION_VERSION  # type: ignore[index]
                    and row["chunk_method"] == chunk_method  # type: ignore[index]
                    and row["embedding_model"] == EMBEDDING_MODEL  # type: ignore[index]
                    and row["embedding_dim"] == EMBEDDING_DIM  # type: ignore[index]
                ):
                    return {
                        "doc_id": actual_id,
                        "status": "deduplicated",
                        "total_chunks": row["total_chunks"],  # type: ignore[index]
                    }
                # Settings changed — delete stale chunks before re-indexing
                await conn.execute(
                    "DELETE FROM document_chunks WHERE document_id = $1 AND user_id = $2",
                    actual_id,
                    user_id,
                )

            await self._store_chunks(conn, actual_id, user_id, chunks, embeddings)

            # For re-indexed docs, update version-related fields now that
            # new chunks are stored.
            if not is_new:
                await conn.execute(
                    """
                    UPDATE documents
                    SET total_chunks = $3,
                        embedding_model = $4,
                        embedding_dim = $5,
                        ingestion_version = $6,
                        chunk_method = $7
                    WHERE id = $1 AND user_id = $2
                    """,
                    actual_id,
                    user_id,
                    len(chunks),
                    EMBEDDING_MODEL,
                    EMBEDDING_DIM,
                    INGESTION_VERSION,
                    chunk_method,
                )

        return {
            "doc_id": actual_id,
            "status": "indexed",
            "total_chunks": len(chunks),
        }

    # -- CRUD -----------------------------------------------------------------

    async def get(self, user_id: str, doc_id: str) -> dict[str, Any] | None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM documents WHERE id = $1 AND user_id = $2",
                doc_id,
                user_id,
            )
        return dict(row) if row else None

    async def list_documents(self, user_id: str) -> list[dict[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, filename, doc_type, total_chunks, file_hash,
                       embedding_model, ingestion_version, indexed_at, updated_at
                FROM documents
                WHERE user_id = $1
                ORDER BY indexed_at DESC
                """,
                user_id,
            )
        return [dict(r) for r in rows]

    async def delete(self, user_id: str, doc_id: str) -> bool:
        """Delete a document (chunks cascade via ON DELETE CASCADE)."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            tag = await conn.execute(
                "DELETE FROM documents WHERE id = $1 AND user_id = $2",
                doc_id,
                user_id,
            )
        return tag == "DELETE 1"

    # -- reindex --------------------------------------------------------------

    async def reindex_document(
        self,
        user_id: str,
        doc_id: str,
        chunks: list[str],
        embeddings: list[Any],
        *,
        chunk_method: str = "rule_based",
    ) -> dict[str, Any]:
        """Re-chunk and re-embed an existing document."""
        pool = await get_pool()
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "DELETE FROM document_chunks WHERE document_id = $1 AND user_id = $2",
                doc_id,
                user_id,
            )
            await self._store_chunks(conn, doc_id, user_id, chunks, embeddings)
            await conn.execute(
                """
                UPDATE documents
                SET total_chunks = $3,
                    embedding_model = $4,
                    embedding_dim = $5,
                    ingestion_version = $6,
                    chunk_method = $7,
                    updated_at = NOW()
                WHERE id = $1 AND user_id = $2
                """,
                doc_id,
                user_id,
                len(chunks),
                EMBEDDING_MODEL,
                EMBEDDING_DIM,
                INGESTION_VERSION,
                chunk_method,
            )
        return {"doc_id": doc_id, "status": "reindexed", "total_chunks": len(chunks)}

    async def list_stale_documents(self, user_id: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Find documents whose ingestion_version is behind current.

        Returns ``id``, ``filename``, ``ingestion_version``, ``chunk_method``,
        and ``content`` so callers can re-chunk without a follow-up query per
        document.
        """
        pool = await get_pool()
        async with pool.acquire() as conn:
            if limit is not None:
                rows = await conn.fetch(
                    """
                    SELECT id, filename, ingestion_version, chunk_method, content
                    FROM documents
                    WHERE user_id = $1
                      AND (ingestion_version IS NULL OR ingestion_version < $2)
                    ORDER BY indexed_at
                    LIMIT $3
                    """,
                    user_id,
                    INGESTION_VERSION,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, filename, ingestion_version, chunk_method, content
                    FROM documents
                    WHERE user_id = $1
                      AND (ingestion_version IS NULL OR ingestion_version < $2)
                    ORDER BY indexed_at
                    """,
                    user_id,
                    INGESTION_VERSION,
                )
        return [dict(r) for r in rows]

    # -- internal -------------------------------------------------------------

    @staticmethod
    async def _store_chunks(
        conn: Any,
        doc_id: str,
        user_id: str,
        chunks: list[str],
        embeddings: list[Any],
    ) -> None:
        """Batch-insert chunk rows."""
        rows = []
        for idx, (text, emb) in enumerate(zip(chunks, embeddings, strict=True)):
            vec = np.asarray(emb, dtype=np.float32).tolist()
            rows.append((str(uuid.uuid4()), doc_id, user_id, idx, text, vec))
        await conn.executemany(
            """
            INSERT INTO document_chunks (id, document_id, user_id, chunk_index, content, embedding)
            VALUES ($1, $2, $3, $4, $5, $6::vector)
            """,
            rows,
        )
