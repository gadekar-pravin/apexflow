"""Tests for api.py — app creation, health endpoints, and router registration."""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers: build the app with mocked heavy dependencies
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Create a TestClient with mocked DB, Firebase, and SkillManager.

    We disable auth, mock the database pool, and mock the skill manager
    so the app boots without any external services.
    """
    monkeypatch.setenv("AUTH_DISABLED", "1")
    monkeypatch.delenv("K_SERVICE", raising=False)

    # Reload auth module to pick up AUTH_DISABLED
    import core.auth

    importlib.reload(core.auth)

    # Mock database init_pool and close_pool so lifespan doesn't need a real DB
    mock_init_pool = AsyncMock()
    mock_close_pool = AsyncMock()
    mock_get_pool = MagicMock(return_value=None)

    with (
        patch("core.database.init_pool", mock_init_pool, create=True),
        patch("core.database.close_pool", mock_close_pool, create=True),
        patch("core.database.get_pool", mock_get_pool),
    ):
        # Need to reload api module to pick up fresh state
        import api as api_module

        importlib.reload(api_module)
        app = api_module.app

        with TestClient(app) as c:
            yield c

    # Cleanup
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    importlib.reload(core.auth)


# ---------------------------------------------------------------------------
# Import check
# ---------------------------------------------------------------------------


def test_api_module_imports() -> None:
    """api module can be imported without errors."""
    import api  # noqa: F401

    assert hasattr(api, "app")


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------


def test_liveness_returns_200(client: TestClient) -> None:
    resp = client.get("/liveness")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "alive"


def test_auth_verify_returns_200_with_auth_disabled(client: TestClient) -> None:
    """GET /api/auth/verify returns 200 with dev-user when AUTH_DISABLED=1."""
    resp = client.get("/api/auth/verify")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["user_id"] == "dev-user"


def test_auth_verify_route_is_registered(client: TestClient) -> None:
    """Auth verify route is registered."""
    paths = _get_route_paths(client)
    assert "/api/auth/verify" in paths


def test_readiness_returns_503_without_pool(client: TestClient) -> None:
    """Without a real DB pool, readiness should return 503."""
    resp = client.get("/readiness")
    # With mock pool returning None, should get 503
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Phase 2 routers are included
# ---------------------------------------------------------------------------


def _get_route_paths(client: TestClient) -> set[str]:
    """Extract all route paths from the app."""
    paths: set[str] = set()
    app = cast(FastAPI, client.app)
    for route in app.routes:
        if hasattr(route, "path"):
            paths.add(route.path)
    return paths


def test_phase2_settings_router(client: TestClient) -> None:
    """Settings routes are registered."""
    paths = _get_route_paths(client)
    assert "/api/settings" in paths


def test_phase2_skills_router(client: TestClient) -> None:
    """Skills routes are registered."""
    paths = _get_route_paths(client)
    assert "/api/skills" in paths


def test_phase2_prompts_router(client: TestClient) -> None:
    """Prompts routes are registered."""
    paths = _get_route_paths(client)
    assert "/api/prompts" in paths


def test_phase2_events_router(client: TestClient) -> None:
    """SSE events route is registered."""
    paths = _get_route_paths(client)
    assert "/api/events" in paths


def test_phase2_news_router(client: TestClient) -> None:
    """News routes are registered."""
    paths = _get_route_paths(client)
    assert "/api/news/sources" in paths or "/api/news/feed" in paths


# ---------------------------------------------------------------------------
# Phase 3 routers are present
# ---------------------------------------------------------------------------


def test_phase3_runs_router(client: TestClient) -> None:
    """Runs routes are registered."""
    paths = _get_route_paths(client)
    assert "/api/runs/execute" in paths


def test_phase3_chat_router(client: TestClient) -> None:
    """Chat routes are registered."""
    paths = _get_route_paths(client)
    assert "/api/chat/sessions" in paths


def test_phase3_rag_router(client: TestClient) -> None:
    """RAG routes are registered."""
    paths = _get_route_paths(client)
    assert "/api/rag/documents" in paths


def test_phase3_remme_router(client: TestClient) -> None:
    """REMME routes are registered."""
    paths = _get_route_paths(client)
    assert "/api/remme/memories" in paths


def test_phase3_inbox_router(client: TestClient) -> None:
    """Inbox routes are registered."""
    paths = _get_route_paths(client)
    assert "/api/inbox" in paths


def test_phase3_cron_router(client: TestClient) -> None:
    """Cron routes are registered."""
    paths = _get_route_paths(client)
    assert "/api/cron/jobs" in paths


def test_phase3_metrics_router(client: TestClient) -> None:
    """Metrics routes are registered."""
    paths = _get_route_paths(client)
    assert "/api/metrics/dashboard" in paths
