"""Prompts router -- v2 with ALLOW_LOCAL_WRITES gate.

Changes from v1:
- PUT/POST return 403 if ALLOW_LOCAL_WRITES env var is unset
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
PROMPTS_BACKUP_DIR = PROMPTS_DIR / ".backup"

ALLOW_LOCAL_WRITES = os.environ.get("ALLOW_LOCAL_WRITES", "").lower() in ("1", "true", "yes")


def _require_writes() -> None:
    if not ALLOW_LOCAL_WRITES:
        raise HTTPException(status_code=403, detail="Local writes disabled. Set ALLOW_LOCAL_WRITES=1.")


class UpdatePromptRequest(BaseModel):
    content: str


@router.get("/prompts")
async def list_prompts() -> dict[str, Any]:
    """List all prompt files with their content."""
    try:
        prompts: list[dict[str, Any]] = []
        if PROMPTS_DIR.exists():
            for f in PROMPTS_DIR.glob("*.md"):
                content = f.read_text()
                backup_file = PROMPTS_BACKUP_DIR / f.name
                prompts.append(
                    {
                        "name": f.stem,
                        "filename": f.name,
                        "content": content,
                        "lines": len(content.splitlines()),
                        "has_backup": backup_file.exists(),
                    }
                )
        return {"status": "success", "prompts": sorted(prompts, key=lambda x: x["name"])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/prompts/{prompt_name}")
async def update_prompt(prompt_name: str, request: UpdatePromptRequest) -> dict[str, Any]:
    """Update a prompt file's content. Creates backup on first edit."""
    _require_writes()
    try:
        prompt_file = PROMPTS_DIR / f"{prompt_name}.md"
        if not prompt_file.exists():
            raise HTTPException(status_code=404, detail=f"Prompt '{prompt_name}' not found")

        PROMPTS_BACKUP_DIR.mkdir(exist_ok=True)
        backup_file = PROMPTS_BACKUP_DIR / f"{prompt_name}.md"
        if not backup_file.exists():
            backup_file.write_text(prompt_file.read_text())

        prompt_file.write_text(request.content)
        return {"status": "success", "message": f"Prompt '{prompt_name}' updated", "has_backup": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/prompts/{prompt_name}/reset")
async def reset_prompt(prompt_name: str) -> dict[str, Any]:
    """Reset a prompt to its original content from backup."""
    _require_writes()
    try:
        prompt_file = PROMPTS_DIR / f"{prompt_name}.md"
        backup_file = PROMPTS_BACKUP_DIR / f"{prompt_name}.md"

        if not backup_file.exists():
            raise HTTPException(status_code=404, detail=f"No backup found for '{prompt_name}'")

        original_content = backup_file.read_text()
        prompt_file.write_text(original_content)
        backup_file.unlink()

        return {
            "status": "success",
            "message": f"Prompt '{prompt_name}' reset to original",
            "content": original_content,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
