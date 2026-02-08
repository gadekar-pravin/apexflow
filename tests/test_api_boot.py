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
# Phase 3+ routers are absent
# ---------------------------------------------------------------------------


def test_phase3_routers_absent(client: TestClient) -> None:
    """Phase 3+ routers (/api/runs, /api/chat, /api/rag, /api/remme) should not exist yet."""
    paths = _get_route_paths(client)
    absent_prefixes = ["/api/runs", "/api/chat", "/api/rag", "/api/remme"]
    for prefix in absent_prefixes:
        matching = [p for p in paths if p.startswith(prefix)]
        assert matching == [], f"Unexpected Phase 3+ route found: {matching}"
