"""Firebase JWT authentication middleware for ApexFlow v2.

- Verifies token from ``Authorization: Bearer <token>``
- Falls back to ``?token=`` query param (for EventSource/SSE which can't send headers)
- Extracts ``user_id`` → ``request.state.user_id``
- Skips for ``/liveness``, ``/readiness``
- ``AUTH_DISABLED=1`` bypasses auth (local dev)
- ``ALLOWED_EMAILS`` (comma-separated) restricts access to listed emails (403 if not in list)
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
_ALLOWED_EMAILS: frozenset[str] | None = (
    frozenset(e.strip().lower() for e in os.environ["ALLOWED_EMAILS"].split(",") if e.strip())
    if os.environ.get("ALLOWED_EMAILS")
    else None
)
# None means open access (any authenticated user); empty string also treated as None
_ALLOWED_EMAILS = _ALLOWED_EMAILS if _ALLOWED_EMAILS else None

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

        # Skip auth for CORS preflight (OPTIONS) — let CORSMiddleware handle them
        if request.method == "OPTIONS":
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

        # Email allowlist check (403 = authenticated but not authorized)
        if _ALLOWED_EMAILS is not None:
            email = claims.get("email", "").lower()
            if email not in _ALLOWED_EMAILS:
                logger.warning("Access denied for email: %s", email)
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Access denied. Your account is not authorized."},
                )

        # Attach user_id to request state
        request.state.user_id = claims.get("uid", claims.get("sub", "unknown"))
        return await call_next(request)


async def get_user_id(request: Request) -> str:
    """FastAPI dependency: extract user_id set by auth middleware."""
    return getattr(request.state, "user_id", "dev-user")
