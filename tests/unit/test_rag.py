"""Tests for Phase 4a RAG system -- stores, search, ingestion, service, config."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers: mock pool (same pattern as test_stores.py)
# ---------------------------------------------------------------------------


def _mock_pool(
    fetchrow: Any = None,
    fetch: Any = None,
    fetchval: Any = None,
    execute: Any = None,
) -> AsyncMock:
    """Create a mock asyncpg pool with a mock connection."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow)
    conn.fetch = AsyncMock(return_value=fetch or [])
    conn.fetchval = AsyncMock(return_value=fetchval)
    conn.execute = AsyncMock(return_value=execute or "UPDATE 1")
    conn.executemany = AsyncMock()

    # transaction context manager
    txn = AsyncMock()
    txn.__aenter__ = AsyncMock(return_value=txn)
    txn.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=txn)

    pool = AsyncMock()
    acq = AsyncMock()
    acq.__aenter__ = AsyncMock(return_value=conn)
    acq.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=acq)

    return pool


# ---------------------------------------------------------------------------
# RAG Config
# ---------------------------------------------------------------------------


class TestRagConfig:
    def test_constants(self) -> None:
        from core.rag.config import (
            EMBEDDING_DIM,
            EMBEDDING_MODEL,
            INGESTION_VERSION,
            RRF_K,
            SEARCH_EXPANSION_FACTOR,
        )

        assert EMBEDDING_MODEL == "text-embedding-004"
        assert EMBEDDING_DIM == 768
        assert INGESTION_VERSION == 1
        assert RRF_K == 60
        assert SEARCH_EXPANSION_FACTOR == 3


# ---------------------------------------------------------------------------
# DocumentStore
# ---------------------------------------------------------------------------


class TestDocumentStore:
    @pytest.mark.asyncio
    async def test_index_new_document(self) -> None:
        from core.stores.document_store import DocumentStore

        row = {"id": "doc-1", "is_new": True}
        pool = _mock_pool(fetchrow=row)
        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=pool)):
            store = DocumentStore()
            result = await store.index_document(
                "u1",
                "test.txt",
                "hello world",
                ["hello", "world"],
                [np.zeros(768), np.zeros(768)],
            )
            assert result["status"] == "indexed"
            assert result["doc_id"] == "doc-1"
            assert result["total_chunks"] == 2

    @pytest.mark.asyncio
    async def test_index_dedup_same_version(self) -> None:
        from core.rag.config import INGESTION_VERSION
        from core.stores.document_store import DocumentStore

        row = {
            "id": "doc-existing",
            "is_new": False,
            "ingestion_version": INGESTION_VERSION,
            "chunk_method": "rule_based",
            "embedding_model": "text-embedding-004",
            "embedding_dim": 768,
            "total_chunks": 2,
        }
        pool = _mock_pool(fetchrow=row)
        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=pool)):
            store = DocumentStore()
            result = await store.index_document(
                "u1",
                "test.txt",
                "hello world",
                ["hello", "world"],
                [np.zeros(768), np.zeros(768)],
            )
            assert result["status"] == "deduplicated"
            assert result["doc_id"] == "doc-existing"

    @pytest.mark.asyncio
    async def test_index_version_mismatch_reindexes(self) -> None:
        from core.stores.document_store import DocumentStore

        row = {"id": "doc-existing", "is_new": False, "ingestion_version": 0}
        pool = _mock_pool(fetchrow=row)
        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=pool)):
            store = DocumentStore()
            result = await store.index_document(
                "u1",
                "test.txt",
                "hello world",
                ["hello", "world"],
                [np.zeros(768), np.zeros(768)],
            )
            assert result["status"] == "indexed"
            # Should have deleted old chunks
            conn = pool.acquire().__aenter__.return_value
            assert conn.execute.called

    @pytest.mark.asyncio
    async def test_get(self) -> None:
        from core.stores.document_store import DocumentStore

        row = {"id": "doc-1", "user_id": "u1", "filename": "test.txt"}
        pool = _mock_pool(fetchrow=row)
        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=pool)):
            store = DocumentStore()
            result = await store.get("u1", "doc-1")
            assert result is not None
            assert result["filename"] == "test.txt"

    @pytest.mark.asyncio
    async def test_get_returns_none_for_missing(self) -> None:
        from core.stores.document_store import DocumentStore

        pool = _mock_pool(fetchrow=None)
        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=pool)):
            store = DocumentStore()
            result = await store.get("u1", "nonexistent")
            assert result is None

    @pytest.mark.asyncio
    async def test_list_documents(self) -> None:
        from core.stores.document_store import DocumentStore

        rows = [
            {
                "id": "doc-1",
                "filename": "a.txt",
                "doc_type": None,
                "total_chunks": 3,
                "file_hash": "abc",
                "embedding_model": "text-embedding-004",
                "ingestion_version": 1,
                "indexed_at": "2026-01-01",
                "updated_at": None,
            },
        ]
        pool = _mock_pool(fetch=rows)
        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=pool)):
            store = DocumentStore()
            result = await store.list_documents("u1")
            assert len(result) == 1
            assert result[0]["filename"] == "a.txt"

    @pytest.mark.asyncio
    async def test_delete(self) -> None:
        from core.stores.document_store import DocumentStore

        pool = _mock_pool(execute="DELETE 1")
        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=pool)):
            store = DocumentStore()
            result = await store.delete("u1", "doc-1")
            assert result is True

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_missing(self) -> None:
        from core.stores.document_store import DocumentStore

        pool = _mock_pool(execute="DELETE 0")
        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=pool)):
            store = DocumentStore()
            result = await store.delete("u1", "nonexistent")
            assert result is False

    @pytest.mark.asyncio
    async def test_reindex_document(self) -> None:
        from core.stores.document_store import DocumentStore

        pool = _mock_pool()
        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=pool)):
            store = DocumentStore()
            result = await store.reindex_document(
                "u1",
                "doc-1",
                ["chunk1", "chunk2"],
                [np.zeros(768), np.zeros(768)],
            )
            assert result["status"] == "reindexed"
            assert result["total_chunks"] == 2
            conn = pool.acquire().__aenter__.return_value
            assert conn.executemany.called

    @pytest.mark.asyncio
    async def test_list_stale_documents(self) -> None:
        from core.stores.document_store import DocumentStore

        rows = [
            {"id": "doc-old", "filename": "old.txt", "ingestion_version": 0},
        ]
        pool = _mock_pool(fetch=rows)
        with patch("core.stores.document_store.get_pool", AsyncMock(return_value=pool)):
            store = DocumentStore()
            result = await store.list_stale_documents("u1")
            assert len(result) == 1
            assert result[0]["id"] == "doc-old"


# ---------------------------------------------------------------------------
# DocumentSearch
# ---------------------------------------------------------------------------


class TestDocumentSearch:
    @pytest.mark.asyncio
    async def test_hybrid_search_returns_results(self) -> None:
        from core.stores.document_search import DocumentSearch

        rows = [
            {
                "chunk_id": "c1",
                "document_id": "doc-1",
                "content": "hello world",
                "chunk_index": 0,
                "rrf_score": 0.032,
                "vector_score": 0.95,
                "text_score": 0.8,
            },
        ]
        pool = _mock_pool(fetch=rows)
        with patch("core.stores.document_search.get_pool", AsyncMock(return_value=pool)):
            search = DocumentSearch()
            results = await search.hybrid_search(
                "u1",
                "hello",
                np.zeros(768),
                limit=5,
            )
            assert len(results) == 1
            assert results[0]["document_id"] == "doc-1"
            assert "rrf_score" in results[0]
            assert "vector_score" in results[0]
            assert "text_score" in results[0]

    @pytest.mark.asyncio
    async def test_hybrid_search_empty(self) -> None:
        from core.stores.document_search import DocumentSearch

        pool = _mock_pool(fetch=[])
        with patch("core.stores.document_search.get_pool", AsyncMock(return_value=pool)):
            search = DocumentSearch()
            results = await search.hybrid_search(
                "u1",
                "nonexistent query",
                np.zeros(768),
                limit=5,
            )
            assert results == []

    @pytest.mark.asyncio
    async def test_hybrid_search_respects_limit(self) -> None:
        from core.stores.document_search import DocumentSearch

        rows = [
            {
                "chunk_id": f"c{i}",
                "document_id": f"doc-{i}",
                "content": f"text {i}",
                "chunk_index": 0,
                "rrf_score": 1.0 / (i + 1),
                "vector_score": 0.9,
                "text_score": 0.5,
            }
            for i in range(10)
        ]
        pool = _mock_pool(fetch=rows)
        with patch("core.stores.document_search.get_pool", AsyncMock(return_value=pool)):
            search = DocumentSearch()
            results = await search.hybrid_search("u1", "test", np.zeros(768), limit=3)
            assert len(results) == 3


# ---------------------------------------------------------------------------
# Ingestion pipeline
# ---------------------------------------------------------------------------


class TestIngestion:
    @pytest.mark.asyncio
    async def test_ingest_document(self) -> None:
        mock_embedding = np.random.rand(768).astype(np.float32)

        with (
            patch("core.rag.ingestion._doc_store.is_duplicate", AsyncMock(return_value=None)),
            patch("core.rag.ingestion.chunk_document", AsyncMock(return_value=["chunk1", "chunk2"])),
            patch("core.rag.ingestion._batch_embed", AsyncMock(return_value=[mock_embedding, mock_embedding])),
            patch(
                "core.rag.ingestion._doc_store.index_document",
                AsyncMock(return_value={"doc_id": "d1", "status": "indexed", "total_chunks": 2}),
            ),
        ):
            from core.rag.ingestion import ingest_document

            result = await ingest_document("u1", "test.txt", "hello world content")
            assert result["status"] == "indexed"
            assert result["total_chunks"] == 2

    @pytest.mark.asyncio
    async def test_ingest_empty_content(self) -> None:
        with (
            patch("core.rag.ingestion._doc_store.is_duplicate", AsyncMock(return_value=None)),
            patch("core.rag.ingestion.chunk_document", AsyncMock(return_value=[])),
        ):
            from core.rag.ingestion import ingest_document

            result = await ingest_document("u1", "empty.txt", "   ")
            assert result["status"] == "empty"
            assert result["total_chunks"] == 0

    @pytest.mark.asyncio
    async def test_embed_query(self) -> None:
        mock_embedding = np.random.rand(768).astype(np.float32)
        with patch("core.rag.ingestion._sync_embed_query", return_value=mock_embedding):
            from core.rag.ingestion import embed_query

            result = await embed_query("search text")
            assert result is not None


# ---------------------------------------------------------------------------
# RAG Service
# ---------------------------------------------------------------------------


class TestRagService:
    def test_registration(self) -> None:
        from services.rag_service import create_rag_service

        svc = create_rag_service()
        assert svc.name == "rag"
        assert len(svc.tools) == 4
        tool_names = {t.name for t in svc.tools}
        assert "index_document" in tool_names
        assert "search_documents" in tool_names
        assert "list_documents" in tool_names
        assert "delete_document" in tool_names

    def test_tool_parameters_updated(self) -> None:
        from services.rag_service import create_rag_service

        svc = create_rag_service()
        index_tool = next(t for t in svc.tools if t.name == "index_document")
        props = index_tool.parameters["properties"]
        assert "filename" in props
        assert "content" in props
        assert "chunk_method" in props

    def test_registers_with_service_registry(self) -> None:
        from core.service_registry import ServiceRegistry
        from services.rag_service import create_rag_service

        registry = ServiceRegistry()
        registry.register_service(create_rag_service())
        tools = registry.get_all_tools()
        names = {t["function"]["name"] for t in tools}
        assert "index_document" in names
        assert "search_documents" in names

    @pytest.mark.asyncio
    async def test_handler_index(self) -> None:
        from core.tool_context import ToolContext
        from services.rag_service import create_rag_service

        svc = create_rag_service()
        assert svc.handler is not None
        ctx = ToolContext(user_id="u1")

        with patch(
            "services.rag_service.ingest_document",
            AsyncMock(return_value={"doc_id": "d1", "status": "indexed", "total_chunks": 2}),
        ):
            result = await svc.handler(
                "index_document",
                {"filename": "test.txt", "content": "hello"},
                ctx,
            )
            assert result["status"] == "indexed"

    @pytest.mark.asyncio
    async def test_handler_search(self) -> None:
        from core.tool_context import ToolContext
        from services.rag_service import create_rag_service

        svc = create_rag_service()
        assert svc.handler is not None
        ctx = ToolContext(user_id="u1")
        mock_results = [{"chunk_id": "c1", "rrf_score": 0.03}]

        with (
            patch("services.rag_service.embed_query", AsyncMock(return_value=np.zeros(768))),
            patch(
                "services.rag_service._doc_search.hybrid_search",
                AsyncMock(return_value=mock_results),
            ),
        ):
            result = await svc.handler("search_documents", {"query": "test"}, ctx)
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_handler_list(self) -> None:
        from core.tool_context import ToolContext
        from services.rag_service import create_rag_service

        svc = create_rag_service()
        assert svc.handler is not None
        ctx = ToolContext(user_id="u1")

        with patch(
            "services.rag_service._doc_store.list_documents",
            AsyncMock(return_value=[{"id": "d1", "filename": "a.txt"}]),
        ):
            result = await svc.handler("list_documents", {}, ctx)
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_handler_delete(self) -> None:
        from core.tool_context import ToolContext
        from services.rag_service import create_rag_service

        svc = create_rag_service()
        assert svc.handler is not None
        ctx = ToolContext(user_id="u1")

        with patch(
            "services.rag_service._doc_store.delete",
            AsyncMock(return_value=True),
        ):
            result = await svc.handler("delete_document", {"doc_id": "d1"}, ctx)
            assert result["deleted"] is True

    @pytest.mark.asyncio
    async def test_handler_rejects_missing_context(self) -> None:
        from core.service_registry import ToolExecutionError
        from services.rag_service import create_rag_service

        svc = create_rag_service()
        assert svc.handler is not None

        with pytest.raises(ToolExecutionError):
            await svc.handler("list_documents", {}, None)
