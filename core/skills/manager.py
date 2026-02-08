from __future__ import annotations

import importlib.util
import inspect
import json
import logging
import re
from pathlib import Path
from types import ModuleType
from typing import Any

from .base import BaseSkill, SkillMetadata

logger = logging.getLogger("skill_manager")


class SkillManager:
    _instance: SkillManager | None = None

    skills_dir: Path
    registry_file: Path
    skill_classes: dict[str, type[BaseSkill]]
    loaded_skills: dict[str, SkillMetadata]
    _registry: dict[str, dict[str, Any]]

    def __new__(cls) -> SkillManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.skills_dir = Path(__file__).parent / "library"
            cls._instance.registry_file = Path(__file__).parent / "registry.json"
            cls._instance.skill_classes = {}
            cls._instance.loaded_skills = {}
            cls._instance._registry = {}
        return cls._instance

    def initialize(self) -> None:
        """Startup: Scan library and rebuild registry automatically"""
        self.scan_and_register()

    def _save_registry(self) -> None:
        """Persist registry to disk if writable (best-effort)."""
        try:
            self.registry_file.write_text(json.dumps(self._registry, indent=2))
        except OSError:
            logger.debug("Registry file not writable (read-only FS), using in-memory only")

    def scan_and_register(self) -> None:
        """
        Auto-Discovery:
        1. Look at every folder in core/skills/library
        2. Try to load 'skill.py'
        3. Find the BaseSkill subclass
        4. Register its metadata
        """
        registry: dict[str, dict[str, Any]] = {}

        if not self.skills_dir.exists():
            return

        for item in self.skills_dir.iterdir():
            if item.is_dir():
                skill_file = item / "skill.py"
                if skill_file.exists():
                    try:
                        skill_class = self._load_skill_class(skill_file)
                        if skill_class:
                            temp_instance = skill_class()
                            meta = temp_instance.get_metadata()

                            registry[meta.name] = {
                                "path": str(item.relative_to(self.skills_dir.parent.parent.parent)),
                                "version": meta.version,
                                "description": meta.description,
                                "intent_triggers": meta.intent_triggers,
                                "class_name": skill_class.__name__,
                            }
                            self.loaded_skills[meta.name] = meta
                            logger.info("Discovered Skill: %s (v%s)", meta.name, meta.version)
                    except Exception as e:
                        logger.error("Failed to load skill at %s: %s", item, e)

        self._registry = registry
        self._save_registry()
        logger.info("Skill Registry Updated. %d skills available.", len(registry))

    def _load_skill_class(self, file_path: Path) -> type[BaseSkill] | None:
        """Dynamically import a Python file and find the Skill class"""
        spec = importlib.util.spec_from_file_location("dynamic_skill", file_path)
        if spec is None or spec.loader is None:
            return None
        module: ModuleType = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        for _name, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and issubclass(obj, BaseSkill) and obj is not BaseSkill:
                return obj
        return None

    def get_skill(self, skill_name: str) -> BaseSkill | None:
        """Get a fresh instance of a skill, loading its class if necessary"""
        if skill_name in self.skill_classes:
            return self.skill_classes[skill_name]()

        if skill_name not in self._registry:
            return None

        info = self._registry[skill_name]
        # Resolve relative path against project root
        root = self.skills_dir.parent.parent.parent
        path = root / info["path"] / "skill.py"

        klass = self._load_skill_class(path)
        if klass:
            self.skill_classes[skill_name] = klass
            return klass()
        return None

    def get_registry(self) -> dict[str, dict[str, Any]]:
        """Return the in-memory registry (no filesystem dependency)."""
        return self._registry

    def match_intent(self, user_query: str) -> str | None:
        """Simple keyword matching with word boundaries"""
        user_query = user_query.lower()

        for name, info in self._registry.items():
            for trigger in info.get("intent_triggers", []):
                pattern = r"\b" + re.escape(trigger.lower()) + r"\b"
                if re.search(pattern, user_query):
                    return name
        return None


skill_manager = SkillManager()
