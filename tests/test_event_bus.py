"""Tests for core/event_bus.py — EventBus publish, subscribe, and unsubscribe."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from core.event_bus import EventBus

# ---------------------------------------------------------------------------
# Fixture: fresh EventBus per test (bypass singleton)
# ---------------------------------------------------------------------------


@pytest.fixture()
def bus() -> Iterator[EventBus]:
    """Create a fresh EventBus instance for isolation (reset singleton)."""
    # Reset singleton so tests are independent
    EventBus._instance = None
    b = EventBus()
    yield b
    # Cleanup: reset singleton after test
    EventBus._instance = None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_and_subscribe(bus: EventBus) -> None:
    """A subscriber receives events published after subscribing."""
    queue = await bus.subscribe()
    await bus.publish("test_event", "test_source", {"key": "value"})

    # The queue should have the published event (+ any replayed history)
    # Drain replay events first, then get the one we published
    events = []
    while not queue.empty():
        events.append(await queue.get())

    # The last event should be ours
    last = events[-1]
    assert last["type"] == "test_event"
    assert last["source"] == "test_source"
    assert last["data"] == {"key": "value"}
    assert "timestamp" in last


@pytest.mark.asyncio
async def test_history_replay_on_subscribe(bus: EventBus) -> None:
    """New subscriber gets up to 5 most recent events replayed."""
    # Publish 3 events before subscribing
    for i in range(3):
        await bus.publish("evt", "src", {"i": i})

    queue = await bus.subscribe()

    # Should have received 3 replayed events
    events = []
    while not queue.empty():
        events.append(await queue.get())
    assert len(events) == 3
    assert events[0]["data"]["i"] == 0
    assert events[2]["data"]["i"] == 2


@pytest.mark.asyncio
async def test_history_replay_caps_at_five(bus: EventBus) -> None:
    """Replay is capped at 5 events, even if history has more."""
    for i in range(10):
        await bus.publish("evt", "src", {"i": i})

    queue = await bus.subscribe()
    events = []
    while not queue.empty():
        events.append(await queue.get())
    assert len(events) == 5
    # Should be the last 5 (indices 5-9)
    assert events[0]["data"]["i"] == 5
    assert events[4]["data"]["i"] == 9


@pytest.mark.asyncio
async def test_multiple_subscribers_receive_same_event(bus: EventBus) -> None:
    """All active subscribers receive the same published event."""
    q1 = await bus.subscribe()
    q2 = await bus.subscribe()

    await bus.publish("shared", "src", {"msg": "hello"})

    # Both queues should have the event (possibly with replay, so drain)
    events_1 = []
    while not q1.empty():
        events_1.append(await q1.get())
    events_2 = []
    while not q2.empty():
        events_2.append(await q2.get())

    # Find the "shared" event in each
    shared_1 = [e for e in events_1 if e["type"] == "shared"]
    shared_2 = [e for e in events_2 if e["type"] == "shared"]
    assert len(shared_1) == 1
    assert len(shared_2) == 1
    assert shared_1[0]["data"] == {"msg": "hello"}
    assert shared_2[0]["data"] == {"msg": "hello"}


@pytest.mark.asyncio
async def test_unsubscribe_cleanup(bus: EventBus) -> None:
    """After unsubscribing, the queue is removed from subscribers list."""
    queue = await bus.subscribe()
    assert queue in bus._subscribers

    bus.unsubscribe(queue)
    assert queue not in bus._subscribers


@pytest.mark.asyncio
async def test_unsubscribe_stops_receiving_events(bus: EventBus) -> None:
    """An unsubscribed queue does not receive new events."""
    queue = await bus.subscribe()

    # Drain any replay
    while not queue.empty():
        await queue.get()

    bus.unsubscribe(queue)
    await bus.publish("after_unsub", "src", {"x": 1})

    assert queue.empty()


@pytest.mark.asyncio
async def test_event_structure(bus: EventBus) -> None:
    """Published events contain timestamp, type, source, and data."""
    queue = await bus.subscribe()
    await bus.publish("type1", "source1", {"foo": "bar"})

    # Drain to get latest
    events = []
    while not queue.empty():
        events.append(await queue.get())

    last = events[-1]
    assert set(last.keys()) == {"timestamp", "type", "source", "data"}
