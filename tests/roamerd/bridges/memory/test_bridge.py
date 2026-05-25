import pytest

from roamerd.bridges.memory.bridge import MemoryBridge, MemorySink
from roamerd.events import Event
from roamerd.kernel import EventBus


@pytest.mark.asyncio
async def test_memory_bridge_buffers_and_flushes_candidates() -> None:
    bus = EventBus()
    sink = MemorySink()
    bridge = MemoryBridge(sink=sink, flush_size=2)
    await bridge.start(bus)

    await bus.publish(
        Event(
            event_type="memory.candidate_raised",
            source="test",
            session_id="s",
            payload={"kind": "interaction", "content": {"text": "a"}},
        )
    )
    await bus.publish(
        Event(
            event_type="memory.candidate_raised",
            source="test",
            session_id="s",
            payload={"kind": "interaction", "content": {"text": "b"}},
        )
    )
    await bus.run_until_idle()

    assert len(sink.delivered) == 2


@pytest.mark.asyncio
async def test_memory_bridge_keeps_buffer_when_delivery_fails() -> None:
    class FailingSink(MemorySink):
        async def deliver(self, candidates):
            raise RuntimeError("gateway down")

    bus = EventBus()
    sink = FailingSink()
    bridge = MemoryBridge(sink=sink, flush_size=1)
    await bridge.start(bus)

    await bus.publish(
        Event(
            event_type="memory.candidate_raised",
            source="test",
            session_id="s",
            payload={"kind": "interaction", "content": {"text": "a"}},
        )
    )
    await bus.run_until_idle()

    assert bridge.buffered_count == 1


@pytest.mark.asyncio
async def test_memory_bridge_publishes_flush_failed_event() -> None:
    class FailingSink(MemorySink):
        async def deliver(self, candidates):
            raise RuntimeError("gateway down")

    bus = EventBus()
    sink = FailingSink()
    bridge = MemoryBridge(sink=sink, flush_size=1)
    events: list[Event] = []

    async def handler(event: Event) -> None:
        events.append(event)

    bus.subscribe("memory.flush_failed", handler)
    await bridge.start(bus)

    await bus.publish(
        Event(
            event_type="memory.candidate_raised",
            source="test",
            session_id="s",
            payload={"kind": "interaction", "content": {"text": "a"}},
        )
    )
    await bus.run_until_idle()

    assert events[0].payload == {
        "reason": "gateway down",
        "buffer_size": 1,
        "failure_count": 1,
    }


@pytest.mark.asyncio
async def test_memory_bridge_truncates_buffer_after_repeated_flush_failures() -> None:
    class FailingSink(MemorySink):
        async def deliver(self, candidates):
            raise RuntimeError("gateway down")

    bus = EventBus()
    sink = FailingSink()
    bridge = MemoryBridge(sink=sink, flush_size=2)
    await bridge.start(bus)

    for index in range(12):
        await bus.publish(
            Event(
                event_type="memory.candidate_raised",
                source="test",
                session_id="s",
                payload={"kind": "interaction", "content": {"index": index}},
            )
        )
        await bus.run_until_idle()

    assert bridge.buffered_count == 6
    assert [candidate["content"]["index"] for candidate in bridge._buffer] == [6, 7, 8, 9, 10, 11]
