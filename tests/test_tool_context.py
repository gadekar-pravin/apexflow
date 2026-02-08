"""Tests for core/tool_context.py — ToolContext creation and properties."""

from __future__ import annotations

import time

from core.tool_context import ToolContext


def test_creation_with_required_user_id() -> None:
    """ToolContext requires user_id and sets sane defaults."""
    ctx = ToolContext(user_id="u-123")
    assert ctx.user_id == "u-123"
    assert ctx.deadline is None
    assert ctx.metadata == {}


def test_default_trace_id_generation() -> None:
    """A 16-char hex trace_id is auto-generated when not supplied."""
    ctx = ToolContext(user_id="u-1")
    assert isinstance(ctx.trace_id, str)
    assert len(ctx.trace_id) == 16
    # Should be valid hex
    int(ctx.trace_id, 16)


def test_trace_id_uniqueness() -> None:
    """Two contexts should get different trace_ids."""
    ctx1 = ToolContext(user_id="u-1")
    ctx2 = ToolContext(user_id="u-2")
    assert ctx1.trace_id != ctx2.trace_id


def test_custom_trace_id() -> None:
    """Caller-supplied trace_id is respected."""
    ctx = ToolContext(user_id="u-1", trace_id="custom-trace")
    assert ctx.trace_id == "custom-trace"


def test_remaining_seconds_no_deadline() -> None:
    """remaining_seconds returns None when no deadline is set."""
    ctx = ToolContext(user_id="u-1")
    assert ctx.remaining_seconds is None


def test_remaining_seconds_with_future_deadline() -> None:
    """remaining_seconds returns positive value for a future deadline."""
    ctx = ToolContext(user_id="u-1", deadline=time.monotonic() + 60.0)
    remaining = ctx.remaining_seconds
    assert remaining is not None
    assert remaining > 0
    assert remaining <= 60.0


def test_remaining_seconds_with_past_deadline() -> None:
    """remaining_seconds returns 0.0 for an expired deadline (clamped)."""
    ctx = ToolContext(user_id="u-1", deadline=time.monotonic() - 10.0)
    assert ctx.remaining_seconds == 0.0


def test_is_expired_no_deadline() -> None:
    """is_expired is False when no deadline is set."""
    ctx = ToolContext(user_id="u-1")
    assert ctx.is_expired is False


def test_is_expired_future_deadline() -> None:
    """is_expired is False when deadline has not passed."""
    ctx = ToolContext(user_id="u-1", deadline=time.monotonic() + 60.0)
    assert ctx.is_expired is False


def test_is_expired_past_deadline() -> None:
    """is_expired is True when deadline has passed."""
    ctx = ToolContext(user_id="u-1", deadline=time.monotonic() - 1.0)
    assert ctx.is_expired is True


def test_metadata_default_dict() -> None:
    """metadata defaults to an empty dict and is mutable."""
    ctx = ToolContext(user_id="u-1")
    ctx.metadata["key"] = "value"
    assert ctx.metadata == {"key": "value"}


def test_metadata_supplied() -> None:
    """Caller-supplied metadata is stored."""
    ctx = ToolContext(user_id="u-1", metadata={"env": "test"})
    assert ctx.metadata["env"] == "test"
