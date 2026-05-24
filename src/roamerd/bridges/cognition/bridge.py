from __future__ import annotations

import asyncio
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
        self._request_lock = asyncio.Lock()
        self._consecutive_failures = 0
        self._circuit_open = False

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
            "correlation_id": event.correlation_id,
        }
        if self._circuit_open:
            await self._publish(
                "cognition.unavailable",
                {"reason": "circuit_open", "correlation_id": event.correlation_id},
                event,
            )
            return
        try:
            async with self._request_lock:
                response = await self._client.request(payload)
            self._consecutive_failures = 0
            response = {**response, "correlation_id": event.correlation_id}
            await self._publish("cognition.response_received", response, event)
        except Exception as exc:
            self._consecutive_failures += 1
            # TODO(phase-c): replace this placeholder with a timed half-open circuit breaker
            # and health event once the real cognition transport adapter is wired in.
            self._circuit_open = self._consecutive_failures >= 3
            await self._publish(
                "cognition.unavailable",
                {"reason": str(exc), "correlation_id": event.correlation_id},
                event,
            )

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
