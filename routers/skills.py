from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from core.skills.manager import skill_manager

router = APIRouter(prefix="/skills", tags=["Skills"])


class SkillInfo(BaseModel):
    name: str
    version: str
    description: str
    intent_triggers: list[str]
    installed: bool = True


@router.get("", response_model=list[SkillInfo])
async def list_skills() -> list[SkillInfo]:
    """List all installed skills."""
    if not skill_manager.loaded_skills:
        skill_manager.initialize()

    skills: list[SkillInfo] = []
    for name, info in skill_manager.get_registry().items():
        skills.append(
            SkillInfo(
                name=name,
                version=info.get("version", "0.0.0"),
                description=info.get("description", ""),
                intent_triggers=info.get("intent_triggers", []),
                installed=True,
            )
        )
    return skills


@router.post("/{skill_id}/install")
async def install_skill(skill_id: str) -> dict[str, str]:
    """Placeholder for remote installation."""
    return {"status": "installed", "message": f"Skill {skill_id} is ready."}
