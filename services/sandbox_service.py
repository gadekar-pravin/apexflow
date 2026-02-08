"""Sandbox service stub -- placeholder for Phase 4c."""

from __future__ import annotations

import logging
from typing import Any

from core.service_registry import (
    ServiceDefinition,
    ToolDefinition,
    ToolExecutionError,
)
from core.tool_context import ToolContext

logger = logging.getLogger(__name__)


async def _handler(name: str, args: dict[str, Any], ctx: ToolContext | None) -> Any:
    raise ToolExecutionError(name, NotImplementedError("Sandbox service not yet available (Phase 4c)"))


def create_sandbox_service() -> ServiceDefinition:
    """Build and return the sandbox stub ServiceDefinition."""
    return ServiceDefinition(
        name="sandbox",
        tools=[
            ToolDefinition(
                name="run_code",
                description="Execute Python code in a sandboxed environment (Phase 4c stub).",
                parameters={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Python code to execute"},
                        "language": {"type": "string", "default": "python"},
                    },
                    "required": ["code"],
                },
            ),
        ],
        handler=_handler,
    )
