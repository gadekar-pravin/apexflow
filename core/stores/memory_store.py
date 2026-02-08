"""Memory store -- CRUD + vector search on the ``memories`` table."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import numpy as np

from core.database import get_pool
from core.rag.config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)


class MemoryStore:
    """Stateless data-access object for the memories table."""

    async def add(
        self,
        user_id: str,
        text: str,
        category: str,
        source: str,
        embedding: Any,
        confidence: float = 1.0,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Insert a memory and return its UUID."""
        memory_id = str(uuid.uuid4())
        vec = np.asarray(embedding, dtype=np.float32).tolist()

        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO memories (id, user_id, text, category, source,
                                      embedding, confidence, embedding_model, metadata)
                VALUES ($1, $2, $3, $4, $5, $6::vector, $7, $8, $9::jsonb)
                """,
                memory_id,
                user_id,
                text,
                category,
                source,
                vec,
                confidence,
                EMBEDDING_MODEL,
                "{}" if metadata is None else __import__("json").dumps(metadata),
            )
        return memory_id

    async def search(
        self,
        user_id: str,
        query_embedding: Any,
        limit: int = 10,
        min_similarity: float | None = None,
    ) -> list[dict[str, Any]]:
        """Top-k vector search with optional similarity threshold."""
        vec = np.asarray(query_embedding, dtype=np.float32).tolist()

        pool = await get_pool()
        async with pool.acquire() as conn:
            if min_similarity is not None:
                rows = await conn.fetch(
                    """
                    SELECT id, text, category, source, confidence,
                           1 - (embedding <=> $1::vector) AS similarity,
                           created_at, metadata
                    FROM memories
                    WHERE user_id = $2
                      AND 1 - (embedding <=> $1::vector) >= $4
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                    """,
                    vec,
                    user_id,
                    limit,
                    min_similarity,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, text, category, source, confidence,
                           1 - (embedding <=> $1::vector) AS similarity,
                           created_at, metadata
                    FROM memories
                    WHERE user_id = $2
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                    """,
                    vec,
                    user_id,
                    limit,
                )
        return [dict(r) for r in rows]

    async def get_all(self, user_id: str) -> list[dict[str, Any]]:
        """Return all memories for a user, newest first."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, text, category, source, confidence,
                       created_at, updated_at, metadata
                FROM memories
                WHERE user_id = $1
                ORDER BY created_at DESC
                """,
                user_id,
            )
        return [dict(r) for r in rows]

    async def delete(self, user_id: str, memory_id: str) -> bool:
        """Delete a memory, scoped to user. Returns True if a row was deleted."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            tag = await conn.execute(
                "DELETE FROM memories WHERE id = $1 AND user_id = $2",
                memory_id,
                user_id,
            )
        return tag == "DELETE 1"

    async def update_text(
        self,
        user_id: str,
        memory_id: str,
        new_text: str,
        new_embedding: Any,
    ) -> bool:
        """Update a memory's text and re-embed. Returns True if a row was updated."""
        vec = np.asarray(new_embedding, dtype=np.float32).tolist()

        pool = await get_pool()
        async with pool.acquire() as conn:
            tag = await conn.execute(
                """
                UPDATE memories
                SET text = $3, embedding = $4::vector,
                    embedding_model = $5, updated_at = NOW()
                WHERE id = $1 AND user_id = $2
                """,
                memory_id,
                user_id,
                new_text,
                vec,
                EMBEDDING_MODEL,
            )
        return tag == "UPDATE 1"
