"""Tests for Phase 4c Monty sandbox."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 8a. AST Preprocessing Tests
# ---------------------------------------------------------------------------


class TestPreprocessAgentCode:
    def test_return_wrapping(self) -> None:
        from tools.monty_sandbox import preprocess_agent_code

        code = "x = 2 + 2\nreturn {'result': x}"
        result = preprocess_agent_code(code, [])
        assert "def __agent_main__():" in result
        assert "__agent_main__()" in result
        assert "    x = 2 + 2" in result

    def test_no_return_unchanged(self) -> None:
        from tools.monty_sandbox import preprocess_agent_code

        code = "x = 2 + 2\ny = x * 3"
        result = preprocess_agent_code(code, [])
        assert result == code

    def test_await_rejected(self) -> None:
        from tools.monty_sandbox import preprocess_agent_code

        code = "result = await some_func()"
        with pytest.raises(ValueError, match="await"):
            preprocess_agent_code(code, [])

    def test_return_in_if_wraps(self) -> None:
        from tools.monty_sandbox import preprocess_agent_code

        code = "if True:\n    return 42"
        result = preprocess_agent_code(code, [])
        assert "def __agent_main__():" in result

    def test_return_inside_def_not_wrapped(self) -> None:
        from tools.monty_sandbox import preprocess_agent_code

        code = "def foo():\n    return 42\nresult = foo()"
        result = preprocess_agent_code(code, [])
        # Should NOT wrap — the return is inside a def, not top-level
        assert "def __agent_main__():" not in result


# ---------------------------------------------------------------------------
# 8b. Security Bypass Tests
# These strings are intentionally dangerous — they are test payloads that
# Monty's language-level isolation MUST block. They are never executed
# directly; they are passed as strings to the sandboxed interpreter.
# ---------------------------------------------------------------------------

SECURITY_BYPASS_VECTORS = [
    pytest.param("import os\nos.listdir('.')", id="os_module"),
    pytest.param("import subprocess\nsubprocess.run(['ls'])", id="subprocess_module"),
    pytest.param("open('/etc/passwd').read()", id="open_file"),
    pytest.param("import socket\nsocket.socket()", id="socket_module"),
    pytest.param("__import__('os')", id="dunder_import"),
    pytest.param("import ctypes", id="ctypes_module"),
]


@pytest.mark.parametrize("code", SECURITY_BYPASS_VECTORS)
@pytest.mark.asyncio
async def test_security_bypass_blocked(code: str) -> None:
    """All security bypass vectors must return status='error'."""
    from core.tool_context import ToolContext
    from tools.monty_sandbox import run_user_code

    ctx = ToolContext(user_id="test-user")
    with patch("tools.monty_sandbox.log_security_event", new_callable=AsyncMock):
        result = await run_user_code(code, None, ctx)
    assert result["status"] == "error", f"Expected error for: {code}"


# ---------------------------------------------------------------------------
# 8c. DoS Protection Tests
# ---------------------------------------------------------------------------


DOS_VECTORS = [
    pytest.param("while True: pass", id="infinite_loop"),
    pytest.param("x = []\nwhile True:\n    x.append('a' * 1000000)", id="memory_bomb"),
    pytest.param("def f(n):\n    return f(n+1)\nf(0)", id="deep_recursion"),
]


@pytest.mark.parametrize("code", DOS_VECTORS)
@pytest.mark.asyncio
async def test_dos_protection(code: str) -> None:
    """DoS vectors must terminate within timeout (error status)."""
    from core.tool_context import ToolContext
    from tools.monty_sandbox import run_user_code

    ctx = ToolContext(user_id="test-user")
    with (
        patch("tools.monty_sandbox.log_security_event", new_callable=AsyncMock),
        patch("config.sandbox_config.DEFAULT_TIMEOUT_SECONDS", 5),
    ):
        result = await run_user_code(code, None, ctx)
    assert result["status"] == "error", f"Expected error for DoS: {code}"


# ---------------------------------------------------------------------------
# 8d. Valid Code Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_arithmetic() -> None:
    from core.tool_context import ToolContext
    from tools.monty_sandbox import run_user_code

    ctx = ToolContext(user_id="test-user")
    result = await run_user_code("return 2 + 2", None, ctx)
    assert result["status"] == "ok"
    assert result["output"] == 4


@pytest.mark.asyncio
async def test_valid_string_ops() -> None:
    from core.tool_context import ToolContext
    from tools.monty_sandbox import run_user_code

    ctx = ToolContext(user_id="test-user")
    result = await run_user_code('return "hello".upper()', None, ctx)
    assert result["status"] == "ok"
    assert result["output"] == "HELLO"


@pytest.mark.asyncio
async def test_valid_dict_ops() -> None:
    from core.tool_context import ToolContext
    from tools.monty_sandbox import run_user_code

    ctx = ToolContext(user_id="test-user")
    code = 'd = {"a": 1, "b": 2}\nreturn d["a"] + d["b"]'
    result = await run_user_code(code, None, ctx)
    assert result["status"] == "ok"
    assert result["output"] == 3


@pytest.mark.asyncio
async def test_no_registry_pure_computation() -> None:
    from core.tool_context import ToolContext
    from tools.monty_sandbox import run_user_code

    ctx = ToolContext(user_id="test-user")
    code = "x = [i**2 for i in range(5)]\nreturn x"
    result = await run_user_code(code, None, ctx)
    assert result["status"] == "ok"
    assert result["output"] == [0, 1, 4, 9, 16]


# ---------------------------------------------------------------------------
# 8e. Tool Allowlist Tests
# ---------------------------------------------------------------------------


class TestToolAllowlist:
    def test_run_code_not_allowed(self) -> None:
        from config.sandbox_config import SANDBOX_ALLOWED_TOOLS

        assert "run_code" not in SANDBOX_ALLOWED_TOOLS

    def test_index_document_not_allowed(self) -> None:
        from config.sandbox_config import SANDBOX_ALLOWED_TOOLS

        assert "index_document" not in SANDBOX_ALLOWED_TOOLS

    def test_web_search_allowed(self) -> None:
        from config.sandbox_config import SANDBOX_ALLOWED_TOOLS

        assert "web_search" in SANDBOX_ALLOWED_TOOLS

    def test_get_sandbox_tools_filters(self) -> None:
        from config.sandbox_config import get_sandbox_tools
        from core.service_registry import ServiceDefinition, ServiceRegistry, ToolDefinition

        registry = ServiceRegistry()

        async def noop_handler(name: str, args: dict[str, Any], ctx: Any) -> Any:
            return None

        svc = ServiceDefinition(
            name="test",
            tools=[
                ToolDefinition(name="web_search", description="search"),
                ToolDefinition(name="run_code", description="run code"),
                ToolDefinition(name="delete_document", description="delete"),
            ],
            handler=noop_handler,
        )
        registry.register_service(svc)

        allowed = get_sandbox_tools(registry)
        assert "web_search" in allowed
        assert "run_code" not in allowed
        assert "delete_document" not in allowed


# ---------------------------------------------------------------------------
# 8f. Security Logging Tests
# ---------------------------------------------------------------------------


class TestSecurityLogging:
    def test_redact_for_logging(self) -> None:
        from tools.monty_sandbox import _redact_for_logging

        code = "x = 1"
        result = _redact_for_logging(code)
        assert "code_hash" in result
        assert len(result["code_hash"]) == 64  # SHA256 hex
        assert result["code_preview"] == "x = 1"
        assert result["code_length"] == 5

    def test_redact_truncates(self) -> None:
        from tools.monty_sandbox import _redact_for_logging

        code = "a" * 600
        result = _redact_for_logging(code, max_length=100)
        assert result["code_preview"].endswith("...")
        assert len(result["code_preview"]) == 103  # 100 + "..."

    @pytest.mark.asyncio
    async def test_log_security_event_sql(self) -> None:
        from tools.monty_sandbox import log_security_event

        mock_conn = AsyncMock()
        mock_pool = AsyncMock()
        acq = AsyncMock()
        acq.__aenter__ = AsyncMock(return_value=mock_conn)
        acq.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=acq)

        from core.tool_context import ToolContext

        ctx = ToolContext(user_id="u1", trace_id="t1")

        with patch("core.database.get_pool", new_callable=AsyncMock, return_value=mock_pool):
            await log_security_event("u1", "test_event", "code here", {"key": "val"}, ctx)

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert call_args[0][0].strip().startswith("INSERT INTO security_logs")
        assert call_args[0][1] == "u1"
        assert call_args[0][2] == "test_event"
        details = json.loads(call_args[0][3])
        assert details["trace_id"] == "t1"
        assert "code_hash" in details
        assert details["key"] == "val"


# ---------------------------------------------------------------------------
# Positional arg mapping
# ---------------------------------------------------------------------------


class TestArgMapping:
    def test_map_with_arg_order(self) -> None:
        from core.service_registry import ToolDefinition
        from tools.monty_sandbox import _map_positional_args

        tool_def = ToolDefinition(
            name="web_search",
            description="search",
            parameters={"type": "object", "properties": {"query": {}, "limit": {}}},
            arg_order=["query", "limit"],
        )
        result = _map_positional_args(tool_def, ["hello", 10])
        assert result == {"query": "hello", "limit": 10}

    def test_map_fallback_to_schema(self) -> None:
        from core.service_registry import ToolDefinition
        from tools.monty_sandbox import _map_positional_args

        tool_def = ToolDefinition(
            name="web_search",
            description="search",
            parameters={"type": "object", "properties": {"query": {}, "limit": {}}},
        )
        result = _map_positional_args(tool_def, ["hello", 10])
        assert result == {"query": "hello", "limit": 10}

    def test_map_empty_args(self) -> None:
        from core.service_registry import ToolDefinition
        from tools.monty_sandbox import _map_positional_args

        tool_def = ToolDefinition(name="t", description="t")
        result = _map_positional_args(tool_def, [])
        assert result == {}
