"""Tests for core/logging_config.py — JSON logging, prompt_hash, ToolTimer."""

from __future__ import annotations

import json
import logging
import time

from core.logging_config import ToolTimer, _JsonFormatter, prompt_hash, setup_logging

# ---------------------------------------------------------------------------
# _JsonFormatter
# ---------------------------------------------------------------------------


def test_json_formatter_produces_valid_json() -> None:
    """Formatter output must be valid JSON with expected keys."""
    formatter = _JsonFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test_logger"
    assert parsed["message"] == "hello world"
    assert "ts" in parsed


def test_json_formatter_includes_extra_fields() -> None:
    """Extra fields (trace_id, tool, etc.) are merged into JSON output."""
    formatter = _JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="tool call",
        args=(),
        exc_info=None,
    )
    record.trace_id = "abc123"
    record.tool = "search"
    record.latency_ms = 42.5

    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["trace_id"] == "abc123"
    assert parsed["tool"] == "search"
    assert parsed["latency_ms"] == 42.5


def test_json_formatter_excludes_none_extras() -> None:
    """Extra fields that are None are not included in output."""
    formatter = _JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="msg",
        args=(),
        exc_info=None,
    )
    output = formatter.format(record)
    parsed = json.loads(output)

    assert "trace_id" not in parsed
    assert "tool" not in parsed


def test_json_formatter_with_exception() -> None:
    """Exception info is included as 'exception' key."""
    formatter = _JsonFormatter()
    try:
        raise ValueError("test error")
    except ValueError:
        import sys

        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="failed",
        args=(),
        exc_info=exc_info,
    )
    output = formatter.format(record)
    parsed = json.loads(output)

    assert "exception" in parsed
    assert "ValueError" in parsed["exception"]


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------


def test_setup_logging_creates_handler() -> None:
    """setup_logging adds a StreamHandler with _JsonFormatter to root logger."""
    root = logging.getLogger()
    # Clear any existing handlers for clean test
    original_handlers = root.handlers[:]
    root.handlers = []

    try:
        setup_logging(level="DEBUG")
        assert len(root.handlers) == 1
        handler = root.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        assert isinstance(handler.formatter, _JsonFormatter)
        assert root.level == logging.DEBUG
    finally:
        # Restore original handlers
        root.handlers = original_handlers


def test_setup_logging_idempotent() -> None:
    """Calling setup_logging twice does not add duplicate handlers."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    root.handlers = []

    try:
        setup_logging(level="INFO")
        count_after_first = len(root.handlers)
        setup_logging(level="INFO")
        assert len(root.handlers) == count_after_first
    finally:
        root.handlers = original_handlers


# ---------------------------------------------------------------------------
# prompt_hash
# ---------------------------------------------------------------------------


def test_prompt_hash_consistent() -> None:
    """Same input always produces the same hash."""
    h1 = prompt_hash("hello world")
    h2 = prompt_hash("hello world")
    assert h1 == h2


def test_prompt_hash_length() -> None:
    """Hash is a 12-char hex string."""
    h = prompt_hash("test prompt")
    assert len(h) == 12
    # Should be valid hex
    int(h, 16)


def test_prompt_hash_different_inputs() -> None:
    """Different inputs produce different hashes."""
    h1 = prompt_hash("input A")
    h2 = prompt_hash("input B")
    assert h1 != h2


# ---------------------------------------------------------------------------
# ToolTimer
# ---------------------------------------------------------------------------


def test_tool_timer_records_elapsed_ms() -> None:
    """ToolTimer captures elapsed time in milliseconds."""
    with ToolTimer() as t:
        time.sleep(0.05)  # 50ms

    assert t.elapsed_ms > 0
    # Should be at least ~50ms (allow some slack for CI)
    assert t.elapsed_ms >= 30


def test_tool_timer_initial_state() -> None:
    """Before entering context, elapsed_ms is 0."""
    t = ToolTimer()
    assert t.elapsed_ms == 0.0


def test_tool_timer_updates_after_exit() -> None:
    """elapsed_ms is set after __exit__."""
    t = ToolTimer()
    t.__enter__()
    time.sleep(0.01)
    t.__exit__(None, None, None)
    assert t.elapsed_ms > 0
