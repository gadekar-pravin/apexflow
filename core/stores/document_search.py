"""Document search -- hybrid vector + full-text search with RRF fusion."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from core.database import get_pool
from core.rag.config import RRF_K, SEARCH_EXPANSION_FACTOR

logger = logging.getLogger(__name__)


class DocumentSearch:
    """Stateless search over the document_chunks table."""

    async def hybrid_search(
        self,
        user_id: str,
        query_text: str,
        query_embedding: Any,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Reciprocal Rank Fusion of vector cosine + full-text ts_rank.

        Returns up to ``limit`` results, deduplicated per document, with
        ``rrf_score``, ``vector_score``, and ``text_score`` for tuning.
        """
        vec = np.asarray(query_embedding, dtype=np.float32).tolist()
        expanded = limit * SEARCH_EXPANSION_FACTOR

        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH vector_ranked AS (
                    SELECT id, document_id, content, chunk_index,
                           1 - (embedding <=> $1::vector) AS vector_score,
                           ROW_NUMBER() OVER (ORDER BY embedding <=> $1::vector) AS rank
                    FROM document_chunks
                    WHERE user_id = $2
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                ),
                text_ranked AS (
                    SELECT id, document_id, content, chunk_index,
                           ts_rank(content_tsv, plainto_tsquery('english', $4)) AS text_score,
                           ROW_NUMBER() OVER (
                               ORDER BY ts_rank(content_tsv, plainto_tsquery('english', $4)) DESC
                           ) AS rank
                    FROM document_chunks
                    WHERE user_id = $2
                      AND content_tsv @@ plainto_tsquery('english', $4)
                    ORDER BY ts_rank(content_tsv, plainto_tsquery('english', $4)) DESC
                    LIMIT $3
                ),
                fused AS (
                    SELECT
                        COALESCE(v.id, t.id) AS chunk_id,
                        COALESCE(v.document_id, t.document_id) AS document_id,
                        COALESCE(v.content, t.content) AS content,
                        COALESCE(v.chunk_index, t.chunk_index) AS chunk_index,
                        COALESCE(v.vector_score, 0) AS vector_score,
                        COALESCE(t.text_score, 0) AS text_score,
                        COALESCE(1.0 / ($5 + v.rank), 0) +
                            COALESCE(1.0 / ($5 + t.rank), 0) AS rrf_score
                    FROM vector_ranked v
                    FULL OUTER JOIN text_ranked t ON v.id = t.id
                )
                SELECT DISTINCT ON (document_id)
                    chunk_id, document_id, content, chunk_index,
                    rrf_score, vector_score, text_score
                FROM fused
                ORDER BY document_id, rrf_score DESC
                """,
                vec,
                user_id,
                expanded,
                query_text,
                RRF_K,
            )

        # Sort by rrf_score descending and apply final limit
        results = [dict(r) for r in rows]
        results.sort(key=lambda r: r["rrf_score"], reverse=True)
        return results[:limit]
