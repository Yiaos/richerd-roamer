import pytest

from roamerd.bridges.cognition.bridge import CognitionBridge, MockCognitionClient
from roamerd.events import Event
from roamerd.kernel import EventBus


@pytest.mark.asyncio
async def test_cognition_bridge_posts_request_and_publishes_response() -> None:
    bus = EventBus()
    client = MockCognitionClient({"action_request": {"action_type": "speech.speak"}})
    bridge = CognitionBridge(client=client, session_id="session-1")
    events: list[Event] = []

    async def handler(event: Event) -> None:
        events.append(event)

    bus.subscribe_pattern("cognition.*", handler)
    await bridge.start(bus)
    await bus.publish(
        Event(
            event_type="cognition.request_needed",
            source="test",
            session_id="session-1",
            turn_id="turn-1",
            payload={"text": "hello"},
        )
    )
    await bus.run_until_idle()

    assert client.requests == [{"text": "hello", "turn_id": "turn-1", "session_id": "session-1"}]
    assert events[-1].event_type == "cognition.response_received"


@pytest.mark.asyncio
async def test_cognition_bridge_unavailable_publishes_degradation() -> None:
    bus = EventBus()
    bridge = CognitionBridge(client=MockCognitionClient(RuntimeError("down")), session_id="s")
    events: list[Event] = []

    async def handler(event: Event) -> None:
        events.append(event)

    bus.subscribe("cognition.unavailable", handler)
    await bridge.start(bus)
    await bus.publish(
        Event(
            event_type="cognition.request_needed",
            source="test",
            session_id="s",
            payload={"text": "hello"},
        )
    )
    await bus.run_until_idle()

    assert events[0].payload["reason"] == "down"
