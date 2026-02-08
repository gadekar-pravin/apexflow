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

    async def index_document(
        self,
        user_id: str,
        filename: str,
        content: str,
        chunks: list[str],
        embeddings: list[Any],
        *,
        doc_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Index a document with its chunks and embeddings.

        Uses content-hash dedup: same user + same hash + same ingestion version
        means the document is already indexed and can be skipped.

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
                     ingestion_version, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb)
                ON CONFLICT (user_id, file_hash) DO UPDATE
                    SET filename = EXCLUDED.filename,
                        doc_type = EXCLUDED.doc_type,
                        content = EXCLUDED.content,
                        total_chunks = EXCLUDED.total_chunks,
                        embedding_model = EXCLUDED.embedding_model,
                        embedding_dim = EXCLUDED.embedding_dim,
                        ingestion_version = EXCLUDED.ingestion_version,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                RETURNING id, (xmax = 0) AS is_new
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
                json.dumps(metadata or {}),
            )

            actual_id: str = row["id"]  # type: ignore[index]
            is_new: bool = row["is_new"]  # type: ignore[index]

            if not is_new:
                # Check if version matches — if so, skip re-chunking
                existing_ver = await conn.fetchval(
                    "SELECT ingestion_version FROM documents WHERE id = $1 AND user_id = $2",
                    actual_id,
                    user_id,
                )
                if existing_ver == INGESTION_VERSION:
                    return {
                        "doc_id": actual_id,
                        "status": "deduplicated",
                        "total_chunks": len(chunks),
                    }
                # Version mismatch — re-index chunks
                await conn.execute(
                    "DELETE FROM document_chunks WHERE document_id = $1 AND user_id = $2",
                    actual_id,
                    user_id,
                )

            await self._store_chunks(conn, actual_id, user_id, chunks, embeddings)

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
                    updated_at = NOW()
                WHERE id = $1 AND user_id = $2
                """,
                doc_id,
                user_id,
                len(chunks),
                EMBEDDING_MODEL,
                EMBEDDING_DIM,
                INGESTION_VERSION,
            )
        return {"doc_id": doc_id, "status": "reindexed", "total_chunks": len(chunks)}

    async def list_stale_documents(self, user_id: str) -> list[dict[str, Any]]:
        """Find documents whose ingestion_version is behind current."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, filename, ingestion_version
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
