"""Tests for core/auth.py — Firebase auth middleware and safety checks."""

from __future__ import annotations

import importlib
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helper: build a minimal app with the middleware
# ---------------------------------------------------------------------------


def _make_app(*, auth_disabled: bool = False) -> FastAPI:
    """Build a tiny FastAPI app with FirebaseAuthMiddleware."""
    app = FastAPI()

    @app.get("/liveness")
    async def liveness() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/readiness")
    async def readiness() -> dict[str, str]:
        return {"status": "ready"}

    @app.get("/api/test")
    async def api_test() -> dict[str, str]:
        return {"user": "ok"}

    # We import the middleware class fresh to pick up patched module vars
    from core.auth import FirebaseAuthMiddleware

    app.add_middleware(FirebaseAuthMiddleware)
    return app


# ---------------------------------------------------------------------------
# AUTH_DISABLED bypass
# ---------------------------------------------------------------------------


def test_auth_disabled_sets_dev_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """When AUTH_DISABLED=1, middleware sets user_id=dev-user and proceeds."""
    monkeypatch.setenv("AUTH_DISABLED", "1")
    monkeypatch.delenv("K_SERVICE", raising=False)

    # Reload the module so _AUTH_DISABLED picks up the new env
    import core.auth

    importlib.reload(core.auth)

    app = FastAPI()

    @app.get("/api/test")
    async def api_test(request: Request) -> dict[str, Any]:
        return {"user_id": request.state.user_id}

    app.add_middleware(core.auth.FirebaseAuthMiddleware)
    client = TestClient(app)

    resp = client.get("/api/test")
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "dev-user"

    # Restore module state
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    importlib.reload(core.auth)


# ---------------------------------------------------------------------------
# check_startup_safety
# ---------------------------------------------------------------------------


def test_check_startup_safety_raises_on_cloud_run_with_auth_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """K_SERVICE + AUTH_DISABLED must raise RuntimeError."""
    monkeypatch.setenv("K_SERVICE", "apexflow-api")
    monkeypatch.setenv("AUTH_DISABLED", "1")

    import core.auth

    importlib.reload(core.auth)

    with pytest.raises(RuntimeError, match="FATAL"):
        core.auth.check_startup_safety()

    # Cleanup
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    importlib.reload(core.auth)


def test_check_startup_safety_ok_without_k_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No K_SERVICE means safety check passes even with AUTH_DISABLED."""
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.setenv("AUTH_DISABLED", "1")

    import core.auth

    importlib.reload(core.auth)

    # Should not raise
    core.auth.check_startup_safety()

    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    importlib.reload(core.auth)


# ---------------------------------------------------------------------------
# Skip paths (health checks)
# ---------------------------------------------------------------------------


def test_skip_paths_no_auth_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """Requests to SKIP_PATHS bypass auth entirely."""
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)

    import core.auth

    importlib.reload(core.auth)

    app = FastAPI()

    @app.get("/liveness")
    async def liveness() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/readiness")
    async def readiness() -> dict[str, str]:
        return {"status": "ready"}

    app.add_middleware(core.auth.FirebaseAuthMiddleware)
    client = TestClient(app)

    # No Authorization header, but these should still succeed
    resp = client.get("/liveness")
    assert resp.status_code == 200

    resp = client.get("/readiness")
    assert resp.status_code == 200

    importlib.reload(core.auth)


# ---------------------------------------------------------------------------
# Missing Authorization header
# ---------------------------------------------------------------------------


def test_missing_auth_header_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """Request to a protected endpoint without auth header returns 401."""
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)

    import core.auth

    importlib.reload(core.auth)

    app = FastAPI()

    @app.get("/api/protected")
    async def protected() -> dict[str, str]:
        return {"secret": "data"}

    app.add_middleware(core.auth.FirebaseAuthMiddleware)
    client = TestClient(app)

    resp = client.get("/api/protected")
    assert resp.status_code == 401
    assert "Missing" in resp.json()["detail"] or "invalid" in resp.json()["detail"].lower()

    importlib.reload(core.auth)


# ---------------------------------------------------------------------------
# Invalid token returns 401
# ---------------------------------------------------------------------------


def test_invalid_token_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """A request with an invalid Bearer token returns 401."""
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)

    import core.auth

    importlib.reload(core.auth)

    # Mock _verify_token to return None (invalid token)
    with patch.object(core.auth, "_verify_token", return_value=None):
        app = FastAPI()

        @app.get("/api/protected")
        async def protected() -> dict[str, str]:
            return {"secret": "data"}

        app.add_middleware(core.auth.FirebaseAuthMiddleware)
        client = TestClient(app)

        resp = client.get("/api/protected", headers={"Authorization": "Bearer bad-token"})
        assert resp.status_code == 401
        assert "Invalid" in resp.json()["detail"] or "expired" in resp.json()["detail"]

    importlib.reload(core.auth)


# ---------------------------------------------------------------------------
# Valid token sets user_id
# ---------------------------------------------------------------------------


def test_valid_token_sets_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """A valid Bearer token results in request.state.user_id being set."""
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)

    import core.auth

    importlib.reload(core.auth)

    claims = {"uid": "firebase-user-42", "sub": "firebase-user-42"}
    with patch.object(core.auth, "_verify_token", return_value=claims):
        app = FastAPI()

        @app.get("/api/whoami")
        async def whoami(request: Request) -> dict[str, Any]:
            return {"user_id": request.state.user_id}

        app.add_middleware(core.auth.FirebaseAuthMiddleware)
        client = TestClient(app)

        resp = client.get("/api/whoami", headers={"Authorization": "Bearer good-token"})
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "firebase-user-42"

    importlib.reload(core.auth)


# ---------------------------------------------------------------------------
# OPTIONS passthrough (CORS preflight)
# ---------------------------------------------------------------------------


def test_options_request_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """OPTIONS requests to protected paths should pass through (for CORS preflight)."""
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)

    import core.auth

    importlib.reload(core.auth)

    app = FastAPI()

    @app.api_route("/api/protected", methods=["GET", "OPTIONS"])
    async def protected() -> dict[str, str]:
        return {"status": "ok"}

    app.add_middleware(core.auth.FirebaseAuthMiddleware)
    client = TestClient(app)

    # OPTIONS should pass through without auth
    resp = client.options("/api/protected")
    assert resp.status_code == 200

    # GET should still require auth
    resp = client.get("/api/protected")
    assert resp.status_code == 401

    importlib.reload(core.auth)
