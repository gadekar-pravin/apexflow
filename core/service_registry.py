"""ServiceRegistry: unified tool/service routing layer for ApexFlow v2.

Replaces MultiMCP from v1.  Services register tool definitions; the
registry routes ``tool_call(name, args, ctx)`` to the correct handler.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from core.tool_context import ToolContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ToolError(Exception):
    """Base exception for tool-related errors."""


class ToolNotFoundError(ToolError):
    """Raised when a tool name is not registered."""


class ToolExecutionError(ToolError):
    """Raised when a registered tool fails during execution."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ToolDefinition:
    """Schema describing a single callable tool.

    ``arg_order`` is used by sandbox tools that receive positional args.
    """

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    arg_order: list[str] | None = None


@dataclass
class ServiceDefinition:
    """A logical grouping of tools (replaces an MCP server)."""

    name: str
    tools: list[ToolDefinition] = field(default_factory=list)
    handler: Callable[..., Awaitable[Any]] | None = None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class ServiceRegistry:
    """Central registry that owns all tool definitions and routes calls.

    Lifecycle::

        registry = ServiceRegistry()
        await registry.initialize()      # optional async setup
        registry.register_service(svc)
        result = await registry.route_tool_call("tool_name", {...}, ctx)
        await registry.shutdown()
    """

    def __init__(self) -> None:
        self._services: dict[str, ServiceDefinition] = {}
        self._tool_index: dict[str, tuple[ServiceDefinition, ToolDefinition]] = {}

    # -- registration -------------------------------------------------------

    def register_service(self, service: ServiceDefinition) -> None:
        """Register a service and index its tools.

        Raises ``ToolError`` on duplicate tool names.
        """
        if service.name in self._services:
            logger.warning("Replacing existing service '%s'", service.name)

        for tool in service.tools:
            if tool.name in self._tool_index:
                existing_svc, _ = self._tool_index[tool.name]
                raise ToolError(
                    f"Tool name collision: '{tool.name}' already registered " f"by service '{existing_svc.name}'"
                )
            self._tool_index[tool.name] = (service, tool)

        self._services[service.name] = service
        logger.info("Registered service '%s' with %d tool(s)", service.name, len(service.tools))

    # -- routing ------------------------------------------------------------

    async def route_tool_call(
        self,
        name: str,
        args: dict[str, Any],
        ctx: ToolContext | None = None,
    ) -> Any:
        """Execute a tool by name.

        Returns the raw Python object produced by the tool handler.
        """
        entry = self._tool_index.get(name)
        if entry is None:
            raise ToolNotFoundError(f"Tool '{name}' is not registered")

        service, tool_def = entry
        if service.handler is None:
            raise ToolExecutionError(f"Service '{service.name}' has no handler for tool '{name}'")

        try:
            return await service.handler(name, args, ctx)
        except ToolError:
            raise
        except Exception as exc:
            raise ToolExecutionError(f"Tool '{name}' failed: {exc}") from exc

    # -- queries ------------------------------------------------------------

    def get_all_tools(self) -> list[dict[str, Any]]:
        """Return all tools in OpenAI-compatible function-calling format."""
        out: list[dict[str, Any]] = []
        for _svc, tool_def in self._tool_index.values():
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool_def.name,
                        "description": tool_def.description,
                        "parameters": tool_def.parameters,
                    },
                }
            )
        return out

    def get_tools_from_servers(self, server_names: list[str]) -> list[dict[str, Any]]:
        """Return tools belonging to the listed service names."""
        out: list[dict[str, Any]] = []
        for svc_name in server_names:
            svc = self._services.get(svc_name)
            if svc is None:
                logger.warning("Service '%s' not found in registry", svc_name)
                continue
            for tool_def in svc.tools:
                out.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool_def.name,
                            "description": tool_def.description,
                            "parameters": tool_def.parameters,
                        },
                    }
                )
        return out

    def function_wrapper(self, name: str) -> Callable[..., Awaitable[Any]] | None:
        """Return a direct async callable for a tool, or None."""
        entry = self._tool_index.get(name)
        if entry is None:
            return None
        service, _tool_def = entry

        async def _wrapper(**kwargs: Any) -> Any:
            return await self.route_tool_call(name, kwargs)

        return _wrapper

    # -- lifecycle ----------------------------------------------------------

    async def initialize(self) -> None:
        """Async startup hook (extend in subclass if needed)."""
        logger.info("ServiceRegistry initialized (empty)")

    async def shutdown(self) -> None:
        """Async shutdown hook."""
        logger.info("ServiceRegistry shutting down")
        self._tool_index.clear()
        self._services.clear()
