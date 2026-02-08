"""Firebase JWT authentication middleware for ApexFlow v2.

- Verifies token from ``Authorization: Bearer <token>``
- Falls back to ``?token=`` query param (for EventSource/SSE which can't send headers)
- Extracts ``user_id`` → ``request.state.user_id``
- Skips for ``/liveness``, ``/readiness``
- ``AUTH_DISABLED=1`` bypasses auth (local dev)
- **FAIL STARTUP** if ``K_SERVICE`` set AND ``AUTH_DISABLED=1``
- Lazy Firebase Admin SDK init
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# Module-level state
_firebase_app: Any = None
_AUTH_DISABLED = os.environ.get("AUTH_DISABLED", "").lower() in ("1", "true", "yes")
_K_SERVICE = os.environ.get("K_SERVICE", "")

# Skip list – paths that never require auth
SKIP_PATHS = {"/liveness", "/readiness", "/docs", "/openapi.json"}


def check_startup_safety() -> None:
    """FAIL STARTUP if running on Cloud Run with auth disabled.

    Must be called during application lifespan before serving requests.
    """
    if _K_SERVICE and _AUTH_DISABLED:
        raise RuntimeError(
            "FATAL: AUTH_DISABLED=1 is not allowed when K_SERVICE is set (Cloud Run). "
            "Remove AUTH_DISABLED to enforce authentication in production."
        )


def _get_firebase_app() -> Any:
    """Lazy-initialize Firebase Admin SDK."""
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    try:
        import firebase_admin
        from firebase_admin import credentials

        # Use Application Default Credentials (ADC) on Cloud Run,
        # or GOOGLE_APPLICATION_CREDENTIALS locally
        cred = credentials.ApplicationDefault()
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized")
        return _firebase_app
    except Exception as e:
        logger.error("Failed to initialize Firebase Admin SDK: %s", e)
        raise


def _verify_token(token: str) -> dict[str, Any] | None:
    """Verify a Firebase ID token and return decoded claims."""
    try:
        from firebase_admin import auth

        _get_firebase_app()
        decoded: dict[str, Any] = auth.verify_id_token(token)
        return decoded
    except Exception as e:
        logger.warning("Token verification failed: %s", e)
        return None


class FirebaseAuthMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that enforces Firebase JWT auth."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip auth for health checks and docs
        if request.url.path in SKIP_PATHS:
            return await call_next(request)

        # Auth disabled (local dev only)
        if _AUTH_DISABLED:
            request.state.user_id = "dev-user"
            return await call_next(request)

        # Extract token from header or query param (EventSource can't send headers)
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Strip "Bearer "
        elif request.query_params.get("token"):
            token = request.query_params["token"]
        else:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid Authorization header"},
            )
        claims = _verify_token(token)

        if claims is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
            )

        # Attach user_id to request state
        request.state.user_id = claims.get("uid", claims.get("sub", "unknown"))
        return await call_next(request)


async def get_user_id(request: Request) -> str:
    """FastAPI dependency: extract user_id set by auth middleware."""
    return getattr(request.state, "user_id", "dev-user")
