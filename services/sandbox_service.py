"""Sandbox service — executes Python code via pydantic-monty subprocess."""

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
    if name != "run_code":
        raise ToolExecutionError(f"Unknown sandbox tool: {name}")

    if ctx is None or not ctx.user_id:
        raise ToolExecutionError("run_code requires a ToolContext with user_id")

    code = args.get("code", "")
    if not code or not code.strip():
        raise ToolExecutionError("run_code requires non-empty 'code' argument")

    from shared.state import get_service_registry
    from tools.monty_sandbox import run_user_code

    registry = get_service_registry()
    result = await run_user_code(code, registry, ctx)

    if result["status"] == "error":
        raise ToolExecutionError(result["error"])

    return result.get("output")


def create_sandbox_service() -> ServiceDefinition:
    """Build and return the sandbox ServiceDefinition."""
    return ServiceDefinition(
        name="sandbox",
        tools=[
            ToolDefinition(
                name="run_code",
                description="Execute Python code in a sandboxed environment.",
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
