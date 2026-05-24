import asyncio

import pytest

from roamerd.bridges.cognition.bridge import CognitionBridge, MockCognitionClient
from roamerd.events import Event
from roamerd.kernel import EventBus
from roamerd.types import JSONDict


class SlowCognitionClient:
    def __init__(self) -> None:
        self.active_requests = 0
        self.max_active_requests = 0
        self.requests: list[JSONDict] = []

    async def request(self, payload: JSONDict) -> JSONDict:
        self.active_requests += 1
        self.max_active_requests = max(self.max_active_requests, self.active_requests)
        self.requests.append(payload)
        await asyncio.sleep(0.01)
        self.active_requests -= 1
        return {"response_type": "speech", "text": payload["text"]}


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
            correlation_id="corr-1",
            payload={"text": "hello"},
        )
    )
    await bus.run_until_idle()

    assert client.requests == [
        {
            "text": "hello",
            "turn_id": "turn-1",
            "session_id": "session-1",
            "correlation_id": "corr-1",
        }
    ]
    assert events[-1].event_type == "cognition.response_received"
    assert events[-1].payload["correlation_id"] == "corr-1"


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


@pytest.mark.asyncio
async def test_cognition_bridge_serializes_in_flight_requests() -> None:
    bus = EventBus()
    client = SlowCognitionClient()
    bridge = CognitionBridge(client=client, session_id="s")
    await bridge.start(bus)

    first = Event(
        event_type="cognition.request_needed",
        source="test",
        session_id="s",
        correlation_id="first",
        payload={"text": "first"},
    )
    second = Event(
        event_type="cognition.request_needed",
        source="test",
        session_id="s",
        correlation_id="second",
        payload={"text": "second"},
    )

    await asyncio.gather(bridge._handle_request(first), bridge._handle_request(second))

    assert client.max_active_requests == 1
    assert [request["correlation_id"] for request in client.requests] == ["first", "second"]
