import asyncio
import time

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


class BlockingCognitionClient:
    def __init__(self) -> None:
        self.requests: list[JSONDict] = []
        self.release = asyncio.Event()

    async def request(self, payload: JSONDict) -> JSONDict:
        self.requests.append(payload)
        await self.release.wait()
        return {"response_type": "speech", "text": payload["text"]}


class SequenceCognitionClient:
    def __init__(self, responses: list[JSONDict | Exception]) -> None:
        self._responses = responses
        self.requests: list[JSONDict] = []

    async def request(self, payload: JSONDict) -> JSONDict:
        self.requests.append(payload)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


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


@pytest.mark.asyncio
async def test_cognition_bridge_circuit_opens_after_three_failures() -> None:
    bus = EventBus()
    client = MockCognitionClient(RuntimeError("down"))
    bridge = CognitionBridge(client=client, session_id="s")
    events: list[Event] = []

    async def handler(event: Event) -> None:
        events.append(event)

    bus.subscribe("cognition.unavailable", handler)
    await bridge.start(bus)

    for index in range(4):
        await bus.publish(
            Event(
                event_type="cognition.request_needed",
                source="test",
                session_id="s",
                correlation_id=f"req-{index}",
                payload={"text": "hello"},
            )
        )
        await bus.run_until_idle()

    assert len(client.requests) == 3
    assert [event.payload["reason"] for event in events] == [
        "down",
        "down",
        "down",
        "circuit_open",
    ]


@pytest.mark.asyncio
async def test_cognition_bridge_half_open_success_closes_circuit() -> None:
    bus = EventBus()
    client = SequenceCognitionClient(
        [
            RuntimeError("down"),
            RuntimeError("down"),
            RuntimeError("down"),
            {"response_type": "speech", "text": "recovered"},
        ]
    )
    bridge = CognitionBridge(client=client, session_id="s", circuit_cooldown_sec=0.01)
    cognition_events: list[Event] = []
    health_events: list[Event] = []

    async def cognition_handler(event: Event) -> None:
        cognition_events.append(event)

    async def health_handler(event: Event) -> None:
        health_events.append(event)

    bus.subscribe_pattern("cognition.*", cognition_handler)
    bus.subscribe("system.health_changed", health_handler)
    await bridge.start(bus)

    for index in range(3):
        await bus.publish(
            Event(
                event_type="cognition.request_needed",
                source="test",
                session_id="s",
                correlation_id=f"fail-{index}",
                payload={"text": "hello"},
            )
        )
        await bus.run_until_idle()

    await asyncio.sleep(0.02)
    await bus.publish(
        Event(
            event_type="cognition.request_needed",
            source="test",
            session_id="s",
            correlation_id="recover",
            payload={"text": "hello"},
        )
    )
    await bus.run_until_idle()

    assert len(client.requests) == 4
    assert cognition_events[-1].event_type == "cognition.response_received"
    assert [event.payload for event in health_events[-3:]] == [
        {
            "component": "cognition",
            "status": "unavailable",
            "kind": "bridge",
        },
        {
            "component": "cognition",
            "status": "degraded",
            "kind": "bridge",
        },
        {
            "component": "cognition",
            "status": "healthy",
            "kind": "bridge",
        },
    ]


@pytest.mark.asyncio
async def test_cognition_bridge_half_open_failure_reopens_circuit() -> None:
    bus = EventBus()
    client = SequenceCognitionClient(
        [
            RuntimeError("down"),
            RuntimeError("down"),
            RuntimeError("down"),
            RuntimeError("still down"),
        ]
    )
    bridge = CognitionBridge(client=client, session_id="s", circuit_cooldown_sec=0.01)
    events: list[Event] = []

    async def handler(event: Event) -> None:
        events.append(event)

    bus.subscribe("cognition.unavailable", handler)
    await bridge.start(bus)

    for index in range(3):
        await bus.publish(
            Event(
                event_type="cognition.request_needed",
                source="test",
                session_id="s",
                correlation_id=f"fail-{index}",
                payload={"text": "hello"},
            )
        )
        await bus.run_until_idle()

    await asyncio.sleep(0.02)
    await bus.publish(
        Event(
            event_type="cognition.request_needed",
            source="test",
            session_id="s",
            correlation_id="half-open-fail",
            payload={"text": "hello"},
        )
    )
    await bus.run_until_idle()
    await bus.publish(
        Event(
            event_type="cognition.request_needed",
            source="test",
            session_id="s",
            correlation_id="blocked",
            payload={"text": "hello"},
        )
    )
    await bus.run_until_idle()

    assert len(client.requests) == 4
    assert [event.payload["reason"] for event in events][-2:] == ["still down", "circuit_open"]


@pytest.mark.asyncio
async def test_cognition_bridge_half_open_allows_only_one_probe() -> None:
    bus = EventBus()
    client = BlockingCognitionClient()
    bridge = CognitionBridge(client=client, session_id="s", circuit_cooldown_sec=0.01)
    unavailable_events: list[Event] = []

    async def handler(event: Event) -> None:
        unavailable_events.append(event)

    bus.subscribe("cognition.unavailable", handler)
    await bridge.start(bus)
    bridge._circuit_state = "open"
    bridge._opened_at = time.monotonic() - 1

    first = Event(
        event_type="cognition.request_needed",
        source="test",
        session_id="s",
        correlation_id="probe",
        payload={"text": "hello"},
    )
    second = Event(
        event_type="cognition.request_needed",
        source="test",
        session_id="s",
        correlation_id="blocked",
        payload={"text": "hello"},
    )
    first_task = asyncio.create_task(bridge._handle_request(first))
    await asyncio.sleep(0)
    await bridge._handle_request(second)
    client.release.set()
    await first_task
    await bus.run_until_idle()

    assert len(client.requests) == 1
    assert unavailable_events[-1].payload == {
        "reason": "circuit_open",
        "correlation_id": "blocked",
    }
