from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class SkillMetadata(BaseModel):
    name: str  # e.g. "market_analyst"
    version: str  # e.g. "1.0.0"
    description: str
    author: str
    intent_triggers: list[str]  # e.g. ["check stock", "market update"]


class SkillContext(BaseModel):
    """Context passed to the skill at runtime"""

    agent_id: str
    run_id: str
    memory: dict[str, Any] = {}
    config: dict[str, Any] = {}


class BaseSkill(ABC):
    def __init__(self, context: SkillContext | None = None) -> None:
        self.context = context or SkillContext(agent_id="system", run_id="init")

    @abstractmethod
    def get_metadata(self) -> SkillMetadata:
        """Return metadata about the skill"""
        pass

    @abstractmethod
    def get_tools(self) -> list[Any]:
        """Return list of tools (functions) this skill provides"""
        pass

    async def on_load(self) -> None:
        """Called when the skill is loaded into memory"""
        return

    async def on_run_start(self, initial_prompt: str) -> str:
        """
        Called before the agent starts.
        Can modify the effective prompt or set up resources.
        """
        return initial_prompt

    async def on_run_success(self, artifact: dict[str, Any]) -> dict[str, Any] | None:
        """
        Called when the agent successfully finishes a run.
        This is where 'Meaningful Action' happens (e.g. saving a file, sending an email).
        Returns optional metadata to be included in notifications.
        """
        return None

    async def on_run_failure(self, error: str) -> None:
        """Called if the run fails"""
        return
