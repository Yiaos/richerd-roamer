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
