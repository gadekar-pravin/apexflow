"""Utility functions for logging in ApexFlow v2.

Replaces v1's Rich-based console logging with standard logging.
Keeps function signatures so callers don't break.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("apexflow")


def log_step(title: str, payload: Any = None, symbol: str = "") -> None:
    """Log a step in the execution pipeline."""
    if payload:
        logger.info("%s %s | %s", symbol, title, payload)
    else:
        logger.info("%s %s", symbol, title)


def log_error(message: str, err: Exception | None = None) -> None:
    """Log an error."""
    if err:
        logger.error("%s — %s", message, err)
    else:
        logger.error("%s", message)
