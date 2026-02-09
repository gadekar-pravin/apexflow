"""
REMME Extractor - Extracts memories AND raw preferences from conversations.

This module handles the LLM-based extraction that produces:
1. Memory commands (add/update/delete) for the FAISS store
2. Raw preferences -> Staging queue (normalized later by Normalizer)

The extractor uses free-form extraction - it doesn't need to know the hub schema.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import json_repair

from config.settings_loader import get_model, settings
from core.model_manager import ModelManager

logger = logging.getLogger(__name__)


class RemmeExtractor:
    """
    Extracts memories and structured preferences from conversations.
    """

    def __init__(self, model: str | None = None) -> None:
        # Use provided model or default from settings
        self.model = model or get_model("memory_extraction")

    async def extract(
        self,
        query: str,
        conversation_history: list[dict[str, Any]],
        existing_memories: list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """
        Extract memories and preferences from conversation.

        Returns:
            Tuple of (memory_commands, preferences_dict)
            - memory_commands: [{"action": "add", "text": "..."}, ...]
            - preferences_dict: {"dietary_style": "vegetarian", ...}
        """

        # 1. Format history into a readable transcript
        transcript = ""
        for msg in conversation_history[-5:]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            transcript += f"{role.upper()}: {content}\n"

        # Add current query
        transcript += f"USER: {query}\n"

        # Format existing memories for the prompt
        memories_str = "NONE"
        if existing_memories:
            memories_str = "\n".join([f"ID: {m['id']} | Fact: {m['text']}" for m in existing_memories])

        # 2. Load extraction prompt
        try:
            prompt_path = Path(__file__).parent.parent / "prompts" / "remme_extraction.md"
            base_prompt = prompt_path.read_text().strip()
        except Exception:
            base_prompt = settings.get("remme", {}).get("extraction_prompt", "Extract facts from conversation.")

        system_prompt = f"""{base_prompt}

EXISTING RELEVANT MEMORIES:
{memories_str}
"""

        full_prompt = f"""{system_prompt}

Conversation:
{transcript}

Extract memories and preferences. Return ONLY valid JSON with this structure:
{{"memories": [{{"action": "add", "text": "..."}}], "preferences": {{}}}}"""

        logger.debug("RemMe Target Model: %s", self.model)

        try:
            model_manager = ModelManager(self.model, provider="gemini")
            result = await model_manager.generate_text(full_prompt)
            response = result.text

            logger.debug("Raw Extraction Output (%d chars): %s...", len(response), response[:200])

            # Parse JSON (with repair for malformed responses)
            return self._parse_extraction_result(response)

        except Exception as e:
            logger.error("Gemini Request Failed: %s", e)
            return [], {}

    def _parse_extraction_result(self, content: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """
        Parse the LLM output into memory commands and preferences.

        Handles multiple formats:
        - New format: {"memories": [...], "preferences": {...}}
        - Legacy format: [{"action": "add", ...}]
        """
        try:
            # Try to extract JSON from response
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                content = content[json_start:json_end]

            # Use json_repair for malformed JSON
            parsed = json_repair.loads(content)

            memories: list[dict[str, Any]] = []
            preferences: dict[str, Any] = {}

            # New dual-output format
            if isinstance(parsed, dict):
                # Extract memories
                if "memories" in parsed:
                    for item in parsed["memories"]:
                        if isinstance(item, dict) and "action" in item:
                            memories.append(item)

                # Extract preferences
                if "preferences" in parsed:
                    preferences = parsed["preferences"] or {}

                # Legacy: handle "commands" key
                elif "commands" in parsed:
                    for item in parsed["commands"]:
                        if isinstance(item, dict) and "action" in item:
                            memories.append(item)

                # Legacy: single action object
                elif "action" in parsed:
                    memories = [parsed]

            # Legacy: list of commands
            elif isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and "action" in item:
                        memories.append(item)
                    elif isinstance(item, str):
                        memories.append({"action": "add", "text": item})

            logger.debug("Parsed %d memories, %d preferences.", len(memories), len(preferences))
            return memories, preferences

        except Exception as e:
            logger.warning("Failed to parse JSON from RemMe: %s... Error: %s", content[:100], e)
            return [], {}

    async def extract_legacy(
        self,
        query: str,
        conversation_history: list[dict[str, Any]],
        existing_memories: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Legacy method that returns only memory commands (for backward compatibility).
        """
        memories, _ = await self.extract(query, conversation_history, existing_memories)
        return memories


def apply_preferences_to_hubs(preferences: dict[str, Any]) -> list[str]:
    """Apply extracted preferences to REMME hubs.

    Deferred to Phase 3 — requires remme.hubs and remme.engines.evidence_log.

    Args:
        preferences: Dict of preference key-value pairs from extraction

    Returns:
        List of changes made (for logging)

    Raises:
        NotImplementedError: Always, until Phase 3 is implemented.
    """
    raise NotImplementedError(
        "apply_preferences_to_hubs is deferred to Phase 3 (requires remme.hubs and remme.engines.evidence_log)"
    )
