"""Search quality tests -- golden queries against hybrid search.

Uses synthetic embeddings designed so cosine similarity ranks correctly.
Requires a real database. Tests are skipped when DB is unavailable.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

_rng = np.random.default_rng(42)


def _make_embedding(base_idx: int, noise: float = 0.05) -> list[float]:
    """Create a synthetic 768-dim embedding centered on a base direction.

    Uses orthogonal base vectors (one-hot at base_idx * 100) with small noise
    so cosine similarity between matching pairs is high (~0.95+) while
    non-matching pairs are near-zero.
    """
    vec = _rng.random(768).astype(np.float32) * noise
    # Set a strong signal in a specific dimension range
    start = base_idx * 100
    vec[start : start + 100] = 1.0
    # L2 normalize
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec = vec / norm
    return [float(x) for x in vec]


# Golden documents
GOLDEN_DOCS: list[dict[str, Any]] = [
    {
        "filename": "python_guide.txt",
        "content": "Python is a high-level programming language known for its readability. "
        "It supports multiple paradigms including object-oriented and functional programming.",
        "base_idx": 0,
    },
    {
        "filename": "machine_learning.txt",
        "content": "Machine learning is a subset of artificial intelligence that uses statistical methods "
        "to enable computers to learn from data without being explicitly programmed.",
        "base_idx": 1,
    },
    {
        "filename": "database_design.txt",
        "content": "Relational database design involves normalizing tables, defining primary and foreign keys, "
        "and creating indexes for query performance optimization.",
        "base_idx": 2,
    },
]

# Golden queries with expected top document
GOLDEN_QUERIES: list[dict[str, Any]] = [
    {
        "query": "programming language readability",
        "base_idx": 0,
        "expected_filename": "python_guide.txt",
    },
    {
        "query": "artificial intelligence statistical learning",
        "base_idx": 1,
        "expected_filename": "machine_learning.txt",
    },
    {
        "query": "SQL tables indexes foreign keys",
        "base_idx": 2,
        "expected_filename": "database_design.txt",
    },
]


@pytest.fixture
async def indexed_docs(db_pool: Any, clean_tables: Any) -> dict[str, str]:
    """Index golden documents into the real database."""
    from core.stores.document_store import DocumentStore

    doc_ids: dict[str, str] = {}
    with patch("core.stores.document_store.get_pool", AsyncMock(return_value=db_pool)):
        store = DocumentStore()
        for doc in GOLDEN_DOCS:
            embedding = _make_embedding(int(doc["base_idx"]))
            result = await store.index_document(
                user_id="search-test-user",
                filename=str(doc["filename"]),
                content=str(doc["content"]),
                chunks=[str(doc["content"])],
                embeddings=[embedding],
            )
            doc_ids[str(doc["filename"])] = result["doc_id"]

    return doc_ids


class TestSearchQuality:
    @pytest.mark.asyncio
    async def test_golden_queries_return_expected_doc(
        self,
        db_pool: Any,
        indexed_docs: dict[str, str],
    ) -> None:
        """Each golden query should return its expected document in the top 3."""
        from core.stores.document_search import DocumentSearch

        with patch("core.stores.document_search.get_pool", AsyncMock(return_value=db_pool)):
            search = DocumentSearch()

            for gq in GOLDEN_QUERIES:
                query_embedding = _make_embedding(int(gq["base_idx"]))
                results = await search.hybrid_search(
                    user_id="search-test-user",
                    query_text=str(gq["query"]),
                    query_embedding=query_embedding,
                    limit=3,
                )

                expected_doc_id = indexed_docs[gq["expected_filename"]]
                result_doc_ids = [r["document_id"] for r in results]
                assert expected_doc_id in result_doc_ids, (
                    f"Query '{gq['query']}' did not return expected doc "
                    f"'{gq['expected_filename']}' in top 3. Got doc_ids: {result_doc_ids}"
                )

    @pytest.mark.asyncio
    async def test_rrf_scores_are_positive(
        self,
        db_pool: Any,
        indexed_docs: dict[str, str],
    ) -> None:
        """All returned results should have positive RRF scores."""
        from core.stores.document_search import DocumentSearch

        with patch("core.stores.document_search.get_pool", AsyncMock(return_value=db_pool)):
            search = DocumentSearch()
            query_embedding = _make_embedding(0)
            results = await search.hybrid_search(
                user_id="search-test-user",
                query_text="programming language",
                query_embedding=query_embedding,
                limit=5,
            )

            assert results, "Expected hybrid_search to return results"
            for r in results:
                assert r["rrf_score"] > 0, f"RRF score should be positive, got {r['rrf_score']}"

    @pytest.mark.asyncio
    async def test_vector_score_dominates_for_matched_embedding(
        self,
        db_pool: Any,
        indexed_docs: dict[str, str],
    ) -> None:
        """When query embedding matches a doc embedding closely, that doc's vector_score should be highest."""
        from core.stores.document_search import DocumentSearch

        with patch("core.stores.document_search.get_pool", AsyncMock(return_value=db_pool)):
            search = DocumentSearch()
            # Query with base_idx=0 should have highest vector_score for python_guide
            query_embedding = _make_embedding(0, noise=0.01)
            results = await search.hybrid_search(
                user_id="search-test-user",
                query_text="random unrelated text",
                query_embedding=query_embedding,
                limit=3,
            )

            assert results, "Expected hybrid_search to return results"
            expected_doc_id = indexed_docs["python_guide.txt"]
            top_vector = max(results, key=lambda r: r["vector_score"])
            assert top_vector["document_id"] == expected_doc_id
