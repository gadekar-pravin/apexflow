"""ToolContext: per-request execution context for tool calls."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolContext:
    """Context carried through every tool invocation in a request.

    Attributes:
        user_id: Authenticated user (required).
        trace_id: Unique correlation ID for the request.
        deadline: Absolute monotonic timestamp (from ``time.monotonic()``)
                  after which the request is expired.
        metadata: Arbitrary key-value bag for callers to attach extra info.
    """

    user_id: str
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    deadline: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def remaining_seconds(self) -> float | None:
        """Seconds until deadline, or None if no deadline set."""
        if self.deadline is None:
            return None
        return max(0.0, self.deadline - time.monotonic())

    @property
    def is_expired(self) -> bool:
        """True when a deadline is set and has passed."""
        if self.deadline is None:
            return False
        return time.monotonic() >= self.deadline
