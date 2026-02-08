"""Tests for Phase 3 routers -- endpoint smoke tests via FastAPI TestClient."""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """TestClient with mocked DB and auth disabled."""
    monkeypatch.setenv("AUTH_DISABLED", "1")
    monkeypatch.delenv("K_SERVICE", raising=False)

    import core.auth

    importlib.reload(core.auth)

    mock_get_pool = AsyncMock(return_value=None)

    with patch("core.database.get_pool", mock_get_pool):
        import api as api_module

        importlib.reload(api_module)
        app = api_module.app

        with TestClient(app) as c:
            yield c

    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    importlib.reload(core.auth)


def _get_route_paths(client: TestClient) -> set[str]:
    app = cast(FastAPI, client.app)
    paths: set[str] = set()
    for route in app.routes:
        if hasattr(route, "path"):
            paths.add(route.path)
    return paths


# ---------------------------------------------------------------------------
# OpenAPI spec includes all Phase 3 endpoints
# ---------------------------------------------------------------------------


def test_openapi_includes_phase3(client: TestClient) -> None:
    """All Phase 3 endpoints appear in the OpenAPI spec."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    paths = set(spec.get("paths", {}).keys())

    expected = [
        "/api/runs/execute",
        "/api/runs",
        "/api/chat/sessions",
        "/api/rag/documents",
        "/api/remme/memories",
        "/api/inbox",
        "/api/cron/jobs",
        "/api/metrics/dashboard",
    ]
    for ep in expected:
        assert ep in paths, f"Missing endpoint in OpenAPI spec: {ep}"


# ---------------------------------------------------------------------------
# RAG endpoints (Phase 4a — backed by stores + ingestion pipeline)
# ---------------------------------------------------------------------------


def test_rag_documents_list(client: TestClient) -> None:
    with patch("routers.rag._doc_store.list_documents", AsyncMock(return_value=[])):
        resp = client.get("/api/rag/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["documents"] == []


def test_rag_search(client: TestClient) -> None:
    mock_results = [
        {
            "chunk_id": "c1",
            "document_id": "d1",
            "content": "hi",
            "chunk_index": 0,
            "rrf_score": 0.03,
            "vector_score": 0.9,
            "text_score": 0.5,
        }
    ]
    with (
        patch("routers.rag.embed_query", AsyncMock(return_value=[0.0] * 768)),
        patch("routers.rag._doc_search.hybrid_search", AsyncMock(return_value=mock_results)),
    ):
        resp = client.post("/api/rag/search", json={"query": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1


def test_rag_index(client: TestClient) -> None:
    with patch(
        "routers.rag.ingest_document",
        AsyncMock(return_value={"doc_id": "d1", "status": "indexed", "total_chunks": 2}),
    ):
        resp = client.post("/api/rag/index", json={"filename": "test.txt", "content": "hello world"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "indexed"


def test_rag_delete(client: TestClient) -> None:
    with patch("routers.rag._doc_store.delete", AsyncMock(return_value=True)):
        resp = client.delete("/api/rag/documents/doc123")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True


# ---------------------------------------------------------------------------
# REMME stub endpoints
# ---------------------------------------------------------------------------


def test_remme_preferences_stub(client: TestClient) -> None:
    resp = client.get("/api/remme/preferences")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"


def test_remme_normalize_stub(client: TestClient) -> None:
    resp = client.post("/api/remme/normalize")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "stub"


def test_remme_staging_stub(client: TestClient) -> None:
    resp = client.get("/api/remme/staging/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pending_count"] == 0


# ---------------------------------------------------------------------------
# Version check
# ---------------------------------------------------------------------------


def test_app_version_phase3(client: TestClient) -> None:
    """App version reflects Phase 3."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert "phase3" in spec.get("info", {}).get("version", "")
