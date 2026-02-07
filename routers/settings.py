"""Settings router -- v2 with ALLOW_LOCAL_WRITES gate.

Changes from v1:
- PUT/POST return 403 if ALLOW_LOCAL_WRITES env var is unset
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config.settings_loader import reload_settings, reset_settings, save_settings

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOW_LOCAL_WRITES = os.environ.get("ALLOW_LOCAL_WRITES", "").lower() in ("1", "true", "yes")


def _require_writes() -> None:
    if not ALLOW_LOCAL_WRITES:
        raise HTTPException(status_code=403, detail="Local writes disabled. Set ALLOW_LOCAL_WRITES=1.")


@router.get("/settings")
async def get_settings() -> dict[str, Any]:
    """Get all current settings from config/settings.json."""
    try:
        current_settings = reload_settings()
        return {"status": "success", "settings": current_settings}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load settings: {e!s}") from e


class UpdateSettingsRequest(BaseModel):
    settings: dict[str, Any]


@router.put("/settings")
async def update_settings(request: UpdateSettingsRequest) -> dict[str, Any]:
    """Update settings and save to config/settings.json."""
    _require_writes()
    try:

        def deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
            for key, value in update.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict) and value:
                    deep_merge(base[key], value)
                else:
                    base[key] = value
            return base

        current = reload_settings()
        deep_merge(current, request.settings)
        save_settings()

        warnings: list[str] = []
        rag_keys = ["chunk_size", "chunk_overlap", "max_chunk_length", "semantic_word_limit"]
        if "rag" in request.settings:
            for key in rag_keys:
                if key in request.settings["rag"]:
                    warnings.append(f"Changed '{key}' - requires re-indexing documents to take effect")

        if "models" in request.settings:
            warnings.append("Agent model changes will take effect on the next run.")
            warnings.append("RAG model changes take effect on next document processing or server restart")

        return {
            "status": "success",
            "message": "Settings saved successfully",
            "warnings": warnings if warnings else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {e!s}") from e


@router.post("/settings/reset")
async def reset_to_defaults() -> dict[str, str]:
    """Reset all settings to default values."""
    _require_writes()
    try:
        reset_settings()
        return {"status": "success", "message": "Settings reset to defaults"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset settings: {e!s}") from e


@router.post("/settings/restart")
async def restart_server() -> dict[str, Any]:
    """Return instructions for manual restart."""
    return {
        "status": "manual_required",
        "message": "Automatic restart is not supported. Please manually restart the server.",
        "instructions": [
            "1. Press Ctrl+C in the terminal",
            "2. Run: uvicorn api:app",
            "3. Refresh the browser",
        ],
    }


@router.get("/gemini/status")
async def get_gemini_status() -> dict[str, Any]:
    """Check if Gemini API key is configured via environment variable."""
    try:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        return {
            "status": "success",
            "configured": bool(api_key),
            "key_preview": f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
