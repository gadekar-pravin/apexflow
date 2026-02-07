"""Tests for core/service_registry.py — ServiceRegistry routing and queries."""

from __future__ import annotations

from typing import Any

import pytest

from core.service_registry import (
    ServiceDefinition,
    ServiceRegistry,
    ToolDefinition,
    ToolError,
    ToolExecutionError,
    ToolNotFoundError,
)
from core.tool_context import ToolContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool(name: str = "echo", description: str = "Echoes input") -> ToolDefinition:
    return ToolDefinition(name=name, description=description, parameters={"type": "object"})


async def _echo_handler(name: str, args: dict[str, Any], ctx: ToolContext | None = None) -> dict[str, Any]:
    return {"echoed": args}


async def _failing_handler(name: str, args: dict[str, Any], ctx: ToolContext | None = None) -> dict[str, Any]:
    raise ValueError("boom")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_service_and_index_tools() -> None:
    reg = ServiceRegistry()
    svc = ServiceDefinition(
        name="svc-a",
        tools=[_make_tool("tool1"), _make_tool("tool2")],
        handler=_echo_handler,
    )
    reg.register_service(svc)
    all_tools = reg.get_all_tools()
    assert len(all_tools) == 2
    names = {t["function"]["name"] for t in all_tools}
    assert names == {"tool1", "tool2"}


def test_collision_raises_tool_error() -> None:
    """Duplicate tool names across services must raise ToolError."""
    reg = ServiceRegistry()
    svc_a = ServiceDefinition(
        name="svc-a",
        tools=[_make_tool("shared_name")],
        handler=_echo_handler,
    )
    svc_b = ServiceDefinition(
        name="svc-b",
        tools=[_make_tool("shared_name")],
        handler=_echo_handler,
    )
    reg.register_service(svc_a)
    with pytest.raises(ToolError, match="Tool name collision"):
        reg.register_service(svc_b)


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_tool_call_success() -> None:
    reg = ServiceRegistry()
    svc = ServiceDefinition(
        name="svc-a",
        tools=[_make_tool("echo")],
        handler=_echo_handler,
    )
    reg.register_service(svc)
    result = await reg.route_tool_call("echo", {"msg": "hi"})
    assert result == {"echoed": {"msg": "hi"}}


@pytest.mark.asyncio
async def test_route_tool_call_with_context() -> None:
    reg = ServiceRegistry()
    svc = ServiceDefinition(
        name="svc-a",
        tools=[_make_tool("echo")],
        handler=_echo_handler,
    )
    reg.register_service(svc)
    ctx = ToolContext(user_id="u-1")
    result = await reg.route_tool_call("echo", {"msg": "hi"}, ctx)
    assert result == {"echoed": {"msg": "hi"}}


@pytest.mark.asyncio
async def test_route_unknown_tool_raises_not_found() -> None:
    reg = ServiceRegistry()
    with pytest.raises(ToolNotFoundError, match="not registered"):
        await reg.route_tool_call("nonexistent", {})


@pytest.mark.asyncio
async def test_route_handler_failure_raises_execution_error() -> None:
    reg = ServiceRegistry()
    svc = ServiceDefinition(
        name="svc-a",
        tools=[_make_tool("fail")],
        handler=_failing_handler,
    )
    reg.register_service(svc)
    with pytest.raises(ToolExecutionError, match="boom"):
        await reg.route_tool_call("fail", {})


@pytest.mark.asyncio
async def test_route_no_handler_raises_execution_error() -> None:
    """Service registered with handler=None should fail."""
    reg = ServiceRegistry()
    svc = ServiceDefinition(
        name="svc-a",
        tools=[_make_tool("orphan")],
        handler=None,
    )
    reg.register_service(svc)
    with pytest.raises(ToolExecutionError, match="no handler"):
        await reg.route_tool_call("orphan", {})


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def test_get_all_tools_format() -> None:
    reg = ServiceRegistry()
    svc = ServiceDefinition(
        name="svc-a",
        tools=[_make_tool("t1", "Desc 1")],
        handler=_echo_handler,
    )
    reg.register_service(svc)
    tools = reg.get_all_tools()
    assert len(tools) == 1
    t = tools[0]
    assert t["type"] == "function"
    assert t["function"]["name"] == "t1"
    assert t["function"]["description"] == "Desc 1"
    assert t["function"]["parameters"] == {"type": "object"}


def test_get_tools_from_servers_filters_correctly() -> None:
    reg = ServiceRegistry()
    svc_a = ServiceDefinition(
        name="svc-a",
        tools=[_make_tool("a1")],
        handler=_echo_handler,
    )
    svc_b = ServiceDefinition(
        name="svc-b",
        tools=[_make_tool("b1"), _make_tool("b2")],
        handler=_echo_handler,
    )
    reg.register_service(svc_a)
    reg.register_service(svc_b)

    # Only request svc-b
    result = reg.get_tools_from_servers(["svc-b"])
    assert len(result) == 2
    names = {t["function"]["name"] for t in result}
    assert names == {"b1", "b2"}


def test_get_tools_from_servers_unknown_service_ignored() -> None:
    reg = ServiceRegistry()
    result = reg.get_tools_from_servers(["nonexistent"])
    assert result == []


# ---------------------------------------------------------------------------
# function_wrapper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_function_wrapper_returns_callable() -> None:
    reg = ServiceRegistry()
    svc = ServiceDefinition(
        name="svc-a",
        tools=[_make_tool("echo")],
        handler=_echo_handler,
    )
    reg.register_service(svc)
    wrapper = reg.function_wrapper("echo")
    assert wrapper is not None
    assert callable(wrapper)
    result = await wrapper(msg="hello")
    assert result == {"echoed": {"msg": "hello"}}


def test_function_wrapper_returns_none_for_unknown() -> None:
    reg = ServiceRegistry()
    assert reg.function_wrapper("nonexistent") is None


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown_clears_state() -> None:
    reg = ServiceRegistry()
    svc = ServiceDefinition(
        name="svc-a",
        tools=[_make_tool("x")],
        handler=_echo_handler,
    )
    reg.register_service(svc)
    assert len(reg.get_all_tools()) == 1
    await reg.shutdown()
    assert len(reg.get_all_tools()) == 0
