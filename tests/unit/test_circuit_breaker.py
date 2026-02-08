"""Tests for core/circuit_breaker.py — CircuitBreaker state transitions."""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest

from core.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    _breakers,
    get_all_breakers,
    get_breaker,
    reset_all_breakers,
)

# ---------------------------------------------------------------------------
# Fixture: clean global registry per test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    """Ensure global breaker registry is clean for each test."""
    _breakers.clear()
    yield
    _breakers.clear()


# ---------------------------------------------------------------------------
# Basic state checks
# ---------------------------------------------------------------------------


def test_initial_state_is_closed() -> None:
    cb = CircuitBreaker(name="test-svc")
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True


def test_success_in_closed_decrements_failure_count() -> None:
    cb = CircuitBreaker(name="test-svc")
    cb.failure_count = 3
    cb.record_success()
    assert cb.failure_count == 2


# ---------------------------------------------------------------------------
# CLOSED -> OPEN after threshold failures
# ---------------------------------------------------------------------------


def test_closed_to_open_after_threshold_failures() -> None:
    cb = CircuitBreaker(name="test-svc", failure_threshold=3)
    assert cb.state == CircuitState.CLOSED

    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED

    cb.record_failure()  # 3rd failure hits threshold
    assert cb.state == CircuitState.OPEN  # type: ignore[comparison-overlap]


def test_open_rejects_calls() -> None:
    cb = CircuitBreaker(name="test-svc", failure_threshold=2)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False


# ---------------------------------------------------------------------------
# OPEN -> HALF_OPEN after recovery timeout
# ---------------------------------------------------------------------------


def test_open_to_half_open_after_recovery_timeout() -> None:
    cb = CircuitBreaker(name="test-svc", failure_threshold=1, recovery_timeout=10.0)
    cb.record_failure()  # Opens the circuit
    assert cb.state == CircuitState.OPEN

    # Simulate time passing beyond recovery_timeout
    cb.last_failure_time = time.time() - 15.0
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN  # type: ignore[comparison-overlap]


def test_open_stays_open_before_timeout() -> None:
    cb = CircuitBreaker(name="test-svc", failure_threshold=1, recovery_timeout=60.0)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    # last_failure_time is recent, so should still be OPEN
    assert cb.can_execute() is False
    assert cb.state == CircuitState.OPEN


# ---------------------------------------------------------------------------
# HALF_OPEN -> CLOSED on sufficient successes
# ---------------------------------------------------------------------------


def test_half_open_to_closed_on_successes() -> None:
    cb = CircuitBreaker(
        name="test-svc",
        failure_threshold=1,
        recovery_timeout=0.0,
        half_open_max_calls=2,
    )
    cb.record_failure()  # -> OPEN
    assert cb.state == CircuitState.OPEN

    # Transition to HALF_OPEN
    cb.can_execute()  # recovery_timeout=0 means immediate transition
    assert cb.state == CircuitState.HALF_OPEN  # type: ignore[comparison-overlap]

    # Record enough successes to close the circuit
    cb.record_success()
    cb.record_success()  # half_open_max_calls=2
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


# ---------------------------------------------------------------------------
# HALF_OPEN -> OPEN on failure
# ---------------------------------------------------------------------------


def test_half_open_to_open_on_failure() -> None:
    cb = CircuitBreaker(
        name="test-svc",
        failure_threshold=1,
        recovery_timeout=0.0,
    )
    cb.record_failure()  # -> OPEN
    cb.can_execute()  # -> HALF_OPEN
    assert cb.state == CircuitState.HALF_OPEN

    cb.record_failure()  # Any failure in HALF_OPEN -> OPEN
    assert cb.state == CircuitState.OPEN  # type: ignore[comparison-overlap]


# ---------------------------------------------------------------------------
# HALF_OPEN limited calls
# ---------------------------------------------------------------------------


def test_half_open_limits_test_calls() -> None:
    cb = CircuitBreaker(
        name="test-svc",
        failure_threshold=1,
        recovery_timeout=0.0,
        half_open_max_calls=2,
    )
    cb.record_failure()  # -> OPEN

    # First call transitions from OPEN to HALF_OPEN (resets half_open_calls=0), returns True
    # Note: the transition call itself does NOT increment half_open_calls
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN

    # Second call: half_open_calls 0 < 2, increments to 1, returns True
    assert cb.can_execute() is True

    # Third call: half_open_calls 1 < 2, increments to 2, returns True
    assert cb.can_execute() is True

    # Fourth call should be rejected (half_open_calls 2 == max 2)
    assert cb.can_execute() is False


# ---------------------------------------------------------------------------
# Threshold configuration
# ---------------------------------------------------------------------------


def test_custom_threshold() -> None:
    cb = CircuitBreaker(name="test-svc", failure_threshold=10)
    for _ in range(9):
        cb.record_failure()
    assert cb.state == CircuitState.CLOSED

    cb.record_failure()  # 10th failure
    assert cb.state == CircuitState.OPEN  # type: ignore[comparison-overlap]


# ---------------------------------------------------------------------------
# force_open / force_close
# ---------------------------------------------------------------------------


def test_force_open() -> None:
    cb = CircuitBreaker(name="test-svc")
    assert cb.state == CircuitState.CLOSED
    cb.force_open()
    assert cb.state == CircuitState.OPEN  # type: ignore[comparison-overlap]
    assert cb.can_execute() is False


def test_force_close() -> None:
    cb = CircuitBreaker(name="test-svc", failure_threshold=1)
    cb.record_failure()  # -> OPEN
    assert cb.state == CircuitState.OPEN
    cb.force_close()
    assert cb.state == CircuitState.CLOSED  # type: ignore[comparison-overlap]
    assert cb.failure_count == 0


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------


def test_get_status() -> None:
    cb = CircuitBreaker(name="my-tool", failure_threshold=5)
    status = cb.get_status()
    assert status["name"] == "my-tool"
    assert status["state"] == "closed"
    assert status["failure_count"] == 0


# ---------------------------------------------------------------------------
# Global registry
# ---------------------------------------------------------------------------


def test_get_breaker_creates_and_caches() -> None:
    b1 = get_breaker("tool-x", failure_threshold=3)
    b2 = get_breaker("tool-x")
    assert b1 is b2
    assert b1.failure_threshold == 3


def test_get_breaker_different_names() -> None:
    b1 = get_breaker("tool-a")
    b2 = get_breaker("tool-b")
    assert b1 is not b2


def test_get_all_breakers() -> None:
    get_breaker("x")
    get_breaker("y")
    all_status = get_all_breakers()
    assert "x" in all_status
    assert "y" in all_status
    assert all_status["x"]["state"] == "closed"


def test_reset_all_breakers() -> None:
    b = get_breaker("z", failure_threshold=1)
    b.record_failure()
    assert b.state == CircuitState.OPEN

    reset_all_breakers()
    assert b.state == CircuitState.CLOSED  # type: ignore[comparison-overlap]
