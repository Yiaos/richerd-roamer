from __future__ import annotations

from typing import Protocol

from roamerd.events import Event
from roamerd.kernel import EventBus
from roamerd.types import JSONDict


class CognitionClient(Protocol):
    async def request(self, payload: JSONDict) -> JSONDict: ...


class MockCognitionClient:
    def __init__(self, response: JSONDict | Exception) -> None:
        self._response = response
        self.requests: list[JSONDict] = []

    async def request(self, payload: JSONDict) -> JSONDict:
        self.requests.append(payload)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class CognitionBridge:
    name = "cognition"

    def __init__(self, *, client: CognitionClient, session_id: str) -> None:
        self._client = client
        self._session_id = session_id
        self._bus: EventBus | None = None

    async def start(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe("cognition.request_needed", self._handle_request)

    async def stop(self) -> None:
        return None

    async def health_check(self) -> str:
        return "healthy"

    async def _handle_request(self, event: Event) -> None:
        text = event.payload.get("text")
        payload: JSONDict = {
            "text": text if isinstance(text, str) else "",
            "turn_id": event.turn_id,
            "session_id": event.session_id,
        }
        try:
            response = await self._client.request(payload)
            await self._publish("cognition.response_received", response, event)
        except Exception as exc:
            await self._publish("cognition.unavailable", {"reason": str(exc)}, event)

    async def _publish(self, event_type: str, payload: JSONDict, source: Event) -> None:
        if self._bus is None:
            return
        await self._bus.publish(
            Event(
                event_type=event_type,
                source="cognition_bridge",
                session_id=self._session_id,
                turn_id=source.turn_id,
                correlation_id=source.correlation_id,
                payload=payload,
            )
        )
