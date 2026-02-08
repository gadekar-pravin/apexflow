"""Monty sandbox: secure code execution via pydantic-monty subprocess.

Provides AST preprocessing, security logging, and the main executor
that spawns a subprocess worker and bridges tool calls via JSON-lines IPC.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

from config.sandbox_config import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_EXTERNAL_CALLS,
    MAX_EXTERNAL_RESPONSE_SIZE,
    MAX_MEMORY_MB,
    MAX_OUTPUT_SIZE,
    get_sandbox_tools,
)
from core.tool_context import ToolContext

logger = logging.getLogger(__name__)

_WORKER_PATH = str(Path(__file__).parent / "_sandbox_worker.py")


# ---------------------------------------------------------------------------
# AST Preprocessing
# ---------------------------------------------------------------------------


def preprocess_agent_code(code: str) -> str:
    """Preprocess agent code for Monty execution.

    Two transforms:
    1. Return wrapping: if top-level ``return`` found, wrap in a function.
    2. Await rejection: if code contains ``await``, raise ValueError.
    """
    tree = ast.parse(code)

    # Check for await
    for node in ast.walk(tree):
        if isinstance(node, ast.Await):
            raise ValueError("Sandbox code must not use 'await'. " "External tool functions are called synchronously.")

    # Check for top-level return (not inside def/class)
    has_return = _has_toplevel_return(tree.body)

    if has_return:
        lines = code.split("\n")
        indented = ["    " + line for line in lines]
        # Monty outputs the last expression's value, so we make the
        # function call result the final expression of the script.
        wrapped = "def __agent_main__():\n" + "\n".join(indented) + "\n__agent_main__()\n"
        return wrapped

    return code


def _has_toplevel_return(stmts: list[ast.stmt]) -> bool:
    """Check if any statement contains a return outside of def/class."""
    for node in stmts:
        if isinstance(node, ast.Return):
            return True
        # Recurse into control flow blocks (if/for/while/try/with)
        # but NOT into def/class
        if isinstance(node, ast.If | ast.For | ast.While | ast.With | ast.AsyncFor | ast.AsyncWith):
            if _has_toplevel_return(node.body):
                return True
            if hasattr(node, "orelse") and _has_toplevel_return(node.orelse):
                return True
        if isinstance(node, ast.Try):
            if _has_toplevel_return(node.body):
                return True
            for handler in node.handlers:
                if _has_toplevel_return(handler.body):
                    return True
            if _has_toplevel_return(node.orelse):
                return True
            if _has_toplevel_return(node.finalbody):
                return True
        if isinstance(node, ast.Match):
            for case in node.cases:
                if _has_toplevel_return(case.body):
                    return True
    return False


# ---------------------------------------------------------------------------
# Security Logging
# ---------------------------------------------------------------------------


def _redact_for_logging(code: str) -> dict[str, Any]:
    """Produce a redacted summary of code for security logging.

    Only stores a non-reversible hash — no plaintext snippets, to avoid
    persisting secrets or PII that may appear in user code.
    """
    return {
        "code_hash": hashlib.sha256(code.encode()).hexdigest(),
        "code_length": len(code),
    }


async def log_security_event(
    user_id: str,
    event_type: str,
    code: str,
    details: dict[str, Any],
    ctx: ToolContext | None = None,
) -> None:
    """Log a security event to the security_logs table."""
    try:
        from core.database import get_pool

        pool = await get_pool()
        redacted = _redact_for_logging(code)
        full_details = {**redacted, **details}
        if ctx:
            full_details["trace_id"] = ctx.trace_id

        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO security_logs (user_id, action, details)
                   VALUES ($1, $2, $3::jsonb)""",
                user_id,
                event_type,
                json.dumps(full_details, default=str),
            )
    except Exception:
        logger.exception("Failed to write security log")


# ---------------------------------------------------------------------------
# Main Executor
# ---------------------------------------------------------------------------


async def run_user_code(
    code: str,
    service_registry: Any | None,
    ctx: ToolContext,
) -> dict[str, Any]:
    """Execute user code in a Monty subprocess sandbox.

    Returns a dict with keys:
      - status: "ok" | "error"
      - output: execution result (on success)
      - error: error message (on failure)
    """
    if not ctx or not ctx.user_id:
        return {"status": "error", "error": "ToolContext with user_id is required"}

    # Determine available tools
    allowed_tools: dict[str, Any] = {}
    if service_registry is not None:
        allowed_tools = get_sandbox_tools(service_registry)
    external_names = list(allowed_tools.keys())

    # Preprocess code
    try:
        processed_code = preprocess_agent_code(code)
    except ValueError as exc:
        return {"status": "error", "error": str(exc)}
    except SyntaxError as exc:
        return {"status": "error", "error": f"Syntax error: {exc}"}

    # Spawn worker subprocess
    timeout: float = float(DEFAULT_TIMEOUT_SECONDS)
    if ctx.remaining_seconds is not None:
        timeout = min(timeout, ctx.remaining_seconds)

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            _WORKER_PATH,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        return {"status": "error", "error": f"Failed to spawn sandbox: {exc}"}

    try:
        result = await asyncio.wait_for(
            _ipc_loop(proc, processed_code, external_names, allowed_tools, service_registry, ctx),
            timeout=timeout,
        )
        return result
    except TimeoutError:
        proc.kill()
        await log_security_event(ctx.user_id, "sandbox_timeout", code, {"timeout": timeout}, ctx)
        return {"status": "error", "error": f"Execution timed out after {timeout}s"}
    except Exception as exc:
        proc.kill()
        await log_security_event(
            ctx.user_id, "sandbox_error", code, {"error": str(exc), "error_type": type(exc).__name__}, ctx
        )
        return {"status": "error", "error": f"Sandbox error: {exc}"}
    finally:
        await proc.wait()


async def _ipc_loop(
    proc: asyncio.subprocess.Process,
    code: str,
    external_names: list[str],
    allowed_tools: dict[str, Any],
    service_registry: Any | None,
    ctx: ToolContext,
) -> dict[str, Any]:
    """Run the IPC loop with the sandbox worker subprocess."""
    assert proc.stdin is not None
    assert proc.stdout is not None

    # Send init message
    init_msg = (
        json.dumps(
            {
                "type": "init",
                "code": code,
                "inputs": {},
                "external_names": external_names,
                "max_external_calls": MAX_EXTERNAL_CALLS,
                "max_memory_mb": MAX_MEMORY_MB,
            }
        )
        + "\n"
    )
    proc.stdin.write(init_msg.encode())
    await proc.stdin.drain()

    # IPC loop
    decode_errors = 0
    while True:
        line = await proc.stdout.readline()
        if not line:
            stderr_bytes = await proc.stderr.read() if proc.stderr else b""
            stderr_text = stderr_bytes.decode(errors="replace").strip()
            return {"status": "error", "error": f"Worker exited unexpectedly: {stderr_text or 'no output'}"}

        try:
            msg = json.loads(line.decode())
            decode_errors = 0
        except json.JSONDecodeError:
            decode_errors += 1
            if decode_errors > 10:
                return {"status": "error", "error": "Too many malformed messages from worker"}
            continue

        msg_type = msg.get("type")

        if msg_type == "done":
            output = msg.get("output")
            output_str = json.dumps(output, default=str) if output is not None else ""
            if len(output_str) > MAX_OUTPUT_SIZE:
                err = f"Output size ({len(output_str)}) exceeds limit ({MAX_OUTPUT_SIZE})"
                return {"status": "error", "error": err}
            return {"status": "ok", "output": output}

        elif msg_type == "error":
            error_msg = msg.get("error", "Unknown error")
            error_type = msg.get("error_type", "Unknown")
            await log_security_event(
                ctx.user_id,
                "sandbox_execution_error",
                code,
                {"error": error_msg, "error_type": error_type},
                ctx,
            )
            return {"status": "error", "error": error_msg}

        elif msg_type == "call":
            func_name = msg.get("name", "")
            call_args = msg.get("args", [])

            if func_name not in allowed_tools or service_registry is None:
                error_resp = json.dumps({"type": "call_error", "error": f"Tool '{func_name}' not allowed"}) + "\n"
                proc.stdin.write(error_resp.encode())
                await proc.stdin.drain()
                continue

            # Map positional args to named params
            tool_def = allowed_tools[func_name]
            named_args = _map_positional_args(tool_def, call_args)

            try:
                tool_result = await service_registry.route_tool_call(func_name, named_args, ctx)
                result_str = json.dumps(tool_result, default=str)
                if len(result_str) > MAX_EXTERNAL_RESPONSE_SIZE:
                    tool_result = {
                        "error": "response_too_large",
                        "message": (
                            f"Tool response ({len(result_str)} bytes)" f" exceeds limit ({MAX_EXTERNAL_RESPONSE_SIZE})"
                        ),
                    }

                resp = json.dumps({"type": "result", "value": tool_result}, default=str) + "\n"
            except Exception as exc:
                resp = json.dumps({"type": "call_error", "error": str(exc)}) + "\n"

            proc.stdin.write(resp.encode())
            await proc.stdin.drain()

        else:
            logger.warning("Unknown message type from worker: %s", msg_type)
            return {"status": "error", "error": f"Unknown worker message type: {msg_type}"}


def _map_positional_args(tool_def: Any, args: list[Any]) -> dict[str, Any]:
    """Map positional args to named params using ToolDefinition.arg_order or schema."""
    if not args:
        return {}

    if tool_def.arg_order:
        param_names = tool_def.arg_order
    else:
        props = tool_def.parameters.get("properties", {})
        param_names = list(props.keys())

    named: dict[str, Any] = {}
    for i, arg in enumerate(args):
        if i < len(param_names):
            named[param_names[i]] = arg
        else:
            named[f"_arg{i}"] = arg

    return named
