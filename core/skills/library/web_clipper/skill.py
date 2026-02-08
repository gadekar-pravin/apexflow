from __future__ import annotations

import logging
import re
from typing import Any

import aiohttp

from core.skills.base import BaseSkill, SkillMetadata

logger = logging.getLogger(__name__)


class WebClipperSkill(BaseSkill):
    def get_metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="web_clipper",
            version="1.0.0",
            description="Downloads and archives web pages",
            author="Arcturus",
            intent_triggers=["clip url", "archive page", "save website", "download html"],
        )

    def get_tools(self) -> list[Any]:
        return []

    async def on_run_start(self, initial_prompt: str) -> str:
        return initial_prompt

    async def on_run_success(self, artifact: dict[str, Any]) -> dict[str, Any] | None:
        # Extract URL from context.config['query']
        query = self.context.config.get("query", "")
        url_match = re.search(r"https?://[^\s]+", query)

        if not url_match:
            logger.warning("Web Clipper: No URL found in query")
            return None

        url = url_match.group(0)

        try:
            async with aiohttp.ClientSession() as session, session.get(url) as resp:
                text = await resp.text()

            # Basic HTML cleanup (placeholder for real parsing)
            clean_text = text[:5000]  # Truncate for safety

            report = f"# Web Clip: {url}\n\n```html\n{clean_text}\n```"

            logger.info("Web Clipper clipped %s (%d chars)", url, len(clean_text))

            return {
                "content": report,
                "type": "web_clip",
                "url": url,
                "summary": f"Clipped {url}",
            }

        except Exception as e:
            logger.error("Web Clipper failed: %s", e)
            return {"error": str(e)}
