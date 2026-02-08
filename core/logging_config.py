"""Structured JSON logging for ApexFlow v2.

Default output includes tool name, latency, success flag, token counts,
prompt hash, and trace_id.  Full prompt/tool-IO content is opt-in via
environment variables:

    LOG_PROMPTS=1   – include raw prompt text
    LOG_TOOL_IO=1   – include tool input/output payloads
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
from typing import Any


class _JsonFormatter(logging.Formatter):
    """Emits one JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Merge any extra keys attached by callers
        for key in ("trace_id", "tool", "latency_ms", "success", "input_tokens", "output_tokens", "prompt_hash"):
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val

        # Opt-in content fields
        if os.environ.get("LOG_PROMPTS") == "1":
            val = getattr(record, "prompt_text", None)
            if val is not None:
                payload["prompt_text"] = val

        if os.environ.get("LOG_TOOL_IO") == "1":
            for key in ("tool_input", "tool_output"):
                val = getattr(record, key, None)
                if val is not None:
                    payload[key] = val

        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            payload["exception"] = record.exc_text

        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with JSON formatter to stderr."""
    root = logging.getLogger()
    if root.handlers:
        return  # already configured

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JsonFormatter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def prompt_hash(text: str) -> str:
    """Return a short SHA-256 prefix for a prompt (for dedup / tracing)."""
    return hashlib.sha256(text.encode()).hexdigest()[:12]


class ToolTimer:
    """Context manager that records tool execution latency.

    Usage::

        with ToolTimer() as t:
            result = await some_tool()
        logger.info("done", extra={"latency_ms": t.elapsed_ms})
    """

    def __init__(self) -> None:
        self._start: float = 0.0
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> ToolTimer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_: object) -> None:
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000
