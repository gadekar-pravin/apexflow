"""ApexFlow v2 – FastAPI entry point.

Lifespan:
- Init DB pool
- Create empty ServiceRegistry
- Optionally init Firebase Admin
- Shutdown: close DB pool

Middleware: CORS + Firebase Auth

Routers: ONLY stream, settings, skills, prompts, news (Phase 2)

Health:
- GET /liveness  → always 200
- GET /readiness → 200 if DB up, 503 if down
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.logging_config import setup_logging
from routers.news import router as news_router
from routers.prompts import router as prompts_router
from routers.settings import router as settings_router
from routers.skills import router as skills_router
from routers.stream import router as stream_router

# Setup structured logging before anything else
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown."""
    # --- Startup ---
    logger.info("ApexFlow v2 starting up...")

    # 1. Auth safety check
    from core.auth import check_startup_safety

    check_startup_safety()

    # 2. Initialize database pool
    from core.database import close_pool, get_pool

    try:
        await get_pool()
        logger.info("Database pool initialized")
    except Exception as e:
        logger.warning("Database pool init failed (non-fatal for Phase 2): %s", e)

    # 3. Create empty ServiceRegistry
    from core.service_registry import ServiceRegistry
    from shared.state import set_service_registry

    registry = ServiceRegistry()
    await registry.initialize()
    set_service_registry(registry)
    logger.info("ServiceRegistry initialized (empty)")

    # 4. Initialize skill manager
    try:
        from core.skills.manager import skill_manager

        skill_manager.initialize()
        logger.info("SkillManager initialized")
    except Exception as e:
        logger.warning("SkillManager init failed (non-fatal): %s", e)

    yield

    # --- Shutdown ---
    logger.info("ApexFlow v2 shutting down...")
    await registry.shutdown()

    try:
        await close_pool()
        logger.info("Database pool closed")
    except Exception as e:
        logger.warning("Database pool close failed: %s", e)


# Create app
app = FastAPI(
    title="ApexFlow v2",
    version="2.0.0-phase2",
    lifespan=lifespan,
)

# --- Middleware ---

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Firebase Auth
auth_disabled = os.environ.get("AUTH_DISABLED", "").lower() in ("1", "true", "yes")
if not auth_disabled:
    try:
        from core.auth import FirebaseAuthMiddleware

        app.add_middleware(FirebaseAuthMiddleware)
        logger.info("Firebase Auth middleware enabled")
    except Exception as e:
        logger.warning("Firebase Auth middleware failed to load: %s", e)
else:
    logger.info("Auth disabled (AUTH_DISABLED=1)")


# --- Health Endpoints ---


@app.get("/liveness")
async def liveness() -> dict[str, str]:
    """Always returns 200 -- proves the process is alive."""
    return {"status": "alive"}


@app.get("/readiness", response_model=None)
async def readiness() -> dict[str, str] | JSONResponse:
    """Returns 200 if DB is reachable, 503 otherwise."""
    try:
        from core.database import get_pool

        pool = await get_pool()
        if pool is None:
            return JSONResponse(status_code=503, content={"status": "not_ready", "reason": "no_pool"})

        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")

        return {"status": "ready"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "not_ready", "reason": str(e)})


# --- Phase 2 Routers ---

app.include_router(stream_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(skills_router, prefix="/api")
app.include_router(prompts_router, prefix="/api")
app.include_router(news_router, prefix="/api")
