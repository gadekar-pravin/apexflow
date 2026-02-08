from __future__ import annotations

import logging
from typing import Any

from core.skills.base import BaseSkill, SkillMetadata

logger = logging.getLogger(__name__)


class MarketAnalystSkill(BaseSkill):
    def get_metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="market_analyst",
            version="1.0.0",
            description="Analyzes stock markets and news using Yahoo Finance and Web Search",
            author="Arcturus System",
            intent_triggers=[
                "stock price",
                "market analysis",
                "news briefing",
                "finance update",
                "price",
                "news",
                "value",
                "funding",
                "market",
            ],
        )

    def get_tools(self) -> list[Any]:
        return []

    async def on_run_start(self, initial_prompt: str) -> str:
        """Inject specific guidance for market analysis"""
        return f"""
        You are the Market Analyst Mode.
        Task: {initial_prompt}

        Instructions:
        1. Use web search tools to find financial data.
        2. Cross-reference with multiple sources if needed.
        3. Be concise and data-driven.
        4. Always include a final 'FormatterAgent' step to produce a cohesive Markdown report.
        """.strip()

    async def on_run_success(self, artifact: dict[str, Any]) -> dict[str, Any] | None:
        """Return the analysis content instead of writing to filesystem."""
        content = artifact.get("summary") or artifact.get("output")

        if content == "Completed." or not content:
            for _k, v in artifact.items():
                if isinstance(v, str) and len(v) > 100:
                    content = v
                    break

        if not content or content == "Completed.":
            content = "Completed."

        if artifact.get("status") == "failed":
            content = f"Analysis Failed: {artifact.get('error', 'Unknown error')}"

        logger.info("Market Analyst produced briefing (%d chars)", len(content))

        return {
            "content": f"# Market Briefing\n\n{content}",
            "type": "briefing",
            "summary": content[:200] + ("..." if len(content) > 200 else ""),
        }
