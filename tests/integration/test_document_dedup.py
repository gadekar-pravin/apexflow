"""Document dedup tests -- SHA256 hash dedup, xmax=0 trick, cascading deletes.

Tests the most PostgreSQL-specific code in the codebase.
Requires a real database. Tests are skipped when DB is unavailable.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

_rng = np.random.default_rng(42)


def _make_embedding(base_idx: int = 0, noise: float = 0.05) -> list[float]:
    """Create a synthetic 768-dim embedding."""
    vec = _rng.random(768).astype(np.float32) * noise
    start = base_idx * 100
    vec[start : start + 100] = 1.0
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec = vec / norm
    return [float(x) for x in vec]


@pytest.mark.asyncio
class TestDocumentDedup:
    """Verify DocumentStore dedup, lifecycle, and cascading behavior."""

    async def test_index_new_document_returns_indexed(
        self, db_pool: Any, clean_tables: None, test_user_id: str
    ) -> None:
        """First-time index returns status='indexed' with correct chunk count."""
        from core.stores.document_store import DocumentStore

        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=db_pool)):
            store = DocumentStore()
            result = await store.index_document(
                test_user_id,
                filename="guide.txt",
                content="Python is great for scripting and automation.",
                chunks=["Python is great", "for scripting and automation."],
                embeddings=[_make_embedding(0), _make_embedding(1)],
            )
            assert result["status"] == "indexed"
            assert result["total_chunks"] == 2
            assert result["doc_id"]

    async def test_index_same_content_twice_returns_deduplicated(
        self, db_pool: Any, clean_tables: None, test_user_id: str
    ) -> None:
        """Same content + same settings = deduplicated (skip)."""
        from core.stores.document_store import DocumentStore

        content = "Duplicate detection test content."

        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=db_pool)):
            store = DocumentStore()
            first = await store.index_document(
                test_user_id,
                filename="dup.txt",
                content=content,
                chunks=[content],
                embeddings=[_make_embedding(0)],
            )
            assert first["status"] == "indexed"

            second = await store.index_document(
                test_user_id,
                filename="dup.txt",
                content=content,
                chunks=[content],
                embeddings=[_make_embedding(0)],
            )
            assert second["status"] == "deduplicated"
            assert second["doc_id"] == first["doc_id"]

    async def test_index_same_hash_different_filename_updates_filename(
        self, db_pool: Any, clean_tables: None, test_user_id: str
    ) -> None:
        """Same content hash with a new filename triggers the ON CONFLICT DO UPDATE branch."""
        from core.stores.document_store import DocumentStore

        content = "Content for filename update test."

        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=db_pool)):
            store = DocumentStore()
            first = await store.index_document(
                test_user_id,
                filename="old_name.txt",
                content=content,
                chunks=[content],
                embeddings=[_make_embedding(0)],
            )

            # Re-index same content with different filename
            second = await store.index_document(
                test_user_id,
                filename="new_name.txt",
                content=content,
                chunks=[content],
                embeddings=[_make_embedding(0)],
            )
            # Should be deduplicated since settings match
            assert second["status"] == "deduplicated"
            assert second["doc_id"] == first["doc_id"]

            # But the filename should have been updated via ON CONFLICT DO UPDATE
            doc = await store.get(test_user_id, first["doc_id"])
            assert doc is not None
            assert doc["filename"] == "new_name.txt"

    async def test_index_different_content_creates_new_doc(
        self, db_pool: Any, clean_tables: None, test_user_id: str
    ) -> None:
        """Different content (different hash) creates a new document."""
        from core.stores.document_store import DocumentStore

        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=db_pool)):
            store = DocumentStore()
            first = await store.index_document(
                test_user_id,
                filename="doc_a.txt",
                content="Content A is unique.",
                chunks=["Content A is unique."],
                embeddings=[_make_embedding(0)],
            )
            second = await store.index_document(
                test_user_id,
                filename="doc_b.txt",
                content="Content B is different.",
                chunks=["Content B is different."],
                embeddings=[_make_embedding(1)],
            )
            assert first["doc_id"] != second["doc_id"]
            assert second["status"] == "indexed"

    async def test_reindex_replaces_chunks(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Reindexing deletes old chunks and inserts new ones."""
        from core.stores.document_store import DocumentStore

        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=db_pool)):
            store = DocumentStore()
            result = await store.index_document(
                test_user_id,
                filename="reindex.txt",
                content="Original content for reindex test.",
                chunks=["Original content", "for reindex test."],
                embeddings=[_make_embedding(0), _make_embedding(1)],
            )
            doc_id = result["doc_id"]
            assert result["total_chunks"] == 2

            # Reindex with 3 chunks
            reindexed = await store.reindex_document(
                test_user_id,
                doc_id,
                chunks=["Chunk 1", "Chunk 2", "Chunk 3"],
                embeddings=[_make_embedding(0), _make_embedding(1), _make_embedding(2)],
            )
            assert reindexed["status"] == "reindexed"
            assert reindexed["total_chunks"] == 3

            # Verify only 3 chunks exist
            async with db_pool.acquire() as conn:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM document_chunks WHERE document_id = $1",
                    doc_id,
                )
            assert count == 3

    async def test_cascading_delete_removes_chunks(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Deleting a document cascades to its chunks via ON DELETE CASCADE."""
        from core.stores.document_store import DocumentStore

        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=db_pool)):
            store = DocumentStore()
            result = await store.index_document(
                test_user_id,
                filename="cascade.txt",
                content="Content for cascade delete test.",
                chunks=["Content for cascade", "delete test."],
                embeddings=[_make_embedding(0), _make_embedding(1)],
            )
            doc_id = result["doc_id"]

            # Verify chunks exist
            async with db_pool.acquire() as conn:
                count = await conn.fetchval("SELECT COUNT(*) FROM document_chunks WHERE document_id = $1", doc_id)
            assert count == 2

            # Delete the document
            deleted = await store.delete(test_user_id, doc_id)
            assert deleted is True

            # Verify chunks are gone
            async with db_pool.acquire() as conn:
                count = await conn.fetchval("SELECT COUNT(*) FROM document_chunks WHERE document_id = $1", doc_id)
            assert count == 0

    async def test_list_stale_documents(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """Documents with older ingestion_version appear in stale list."""
        from core.stores.document_store import DocumentStore

        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=db_pool)):
            store = DocumentStore()
            # Index a document (uses current INGESTION_VERSION)
            result = await store.index_document(
                test_user_id,
                filename="stale_test.txt",
                content="Content for stale test.",
                chunks=["Content for stale test."],
                embeddings=[_make_embedding(0)],
            )
            doc_id = result["doc_id"]

            # Manually set ingestion_version to 0 to simulate staleness
            async with db_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE documents SET ingestion_version = 0 WHERE id = $1",
                    doc_id,
                )

            stale = await store.list_stale_documents(test_user_id)
            assert len(stale) == 1
            assert stale[0]["id"] == doc_id

    async def test_batch_chunk_insertion_via_executemany(
        self, db_pool: Any, clean_tables: None, test_user_id: str
    ) -> None:
        """50 chunks are inserted in a single executemany batch."""
        from core.stores.document_store import DocumentStore

        chunks = [f"Chunk number {i}" for i in range(50)]
        embeddings = [_make_embedding(i % 7) for i in range(50)]

        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=db_pool)):
            store = DocumentStore()
            result = await store.index_document(
                test_user_id,
                filename="batch_test.txt",
                content="Batch insertion test with 50 chunks.",
                chunks=chunks,
                embeddings=embeddings,
            )
            assert result["total_chunks"] == 50

            async with db_pool.acquire() as conn:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM document_chunks WHERE document_id = $1",
                    result["doc_id"],
                )
            assert count == 50

    async def test_get_and_list_documents(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """CRUD roundtrip: index, get, list."""
        from core.stores.document_store import DocumentStore

        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=db_pool)):
            store = DocumentStore()
            result = await store.index_document(
                test_user_id,
                filename="roundtrip.txt",
                content="Roundtrip CRUD test.",
                chunks=["Roundtrip CRUD test."],
                embeddings=[_make_embedding(0)],
            )
            doc_id = result["doc_id"]

            doc = await store.get(test_user_id, doc_id)
            assert doc is not None
            assert doc["filename"] == "roundtrip.txt"

            docs = await store.list_documents(test_user_id)
            assert len(docs) == 1
            assert docs[0]["id"] == doc_id

    async def test_is_duplicate_returns_match(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """is_duplicate returns a match when content + settings match."""
        from core.stores.document_store import DocumentStore

        content = "Content for is_duplicate test."

        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=db_pool)):
            store = DocumentStore()
            result = await store.index_document(
                test_user_id,
                filename="is_dup.txt",
                content=content,
                chunks=[content],
                embeddings=[_make_embedding(0)],
            )
            dup = await store.is_duplicate(test_user_id, content, "rule_based")
            assert dup is not None
            assert dup["doc_id"] == result["doc_id"]
            assert dup["status"] == "deduplicated"

    async def test_is_duplicate_returns_none_for_different_content(
        self, db_pool: Any, clean_tables: None, test_user_id: str
    ) -> None:
        """is_duplicate returns None when content hash doesn't match."""
        from core.stores.document_store import DocumentStore

        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=db_pool)):
            store = DocumentStore()
            await store.index_document(
                test_user_id,
                filename="existing.txt",
                content="Existing document content.",
                chunks=["Existing document content."],
                embeddings=[_make_embedding(0)],
            )
            dup = await store.is_duplicate(test_user_id, "Completely different content.", "rule_based")
            assert dup is None

    async def test_fulltext_search_generated_column(self, db_pool: Any, clean_tables: None, test_user_id: str) -> None:
        """content_tsv GENERATED ALWAYS column populates from content."""
        from core.stores.document_store import DocumentStore

        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=db_pool)):
            store = DocumentStore()
            result = await store.index_document(
                test_user_id,
                filename="fts.txt",
                content="PostgreSQL database indexing and full-text search.",
                chunks=["PostgreSQL database indexing and full-text search."],
                embeddings=[_make_embedding(0)],
            )

        # Query the generated tsvector column directly
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT content_tsv IS NOT NULL AS has_tsv FROM document_chunks WHERE document_id = $1",
                result["doc_id"],
            )
            assert row is not None
            assert row["has_tsv"] is True

            # Full-text match should work
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM document_chunks "
                "WHERE document_id = $1 AND content_tsv @@ plainto_tsquery('english', 'PostgreSQL indexing')",
                result["doc_id"],
            )
            assert count == 1
