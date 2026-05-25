from __future__ import annotations

import asyncio
import time
from typing import Literal, Protocol

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

    def __init__(
        self,
        *,
        client: CognitionClient,
        session_id: str,
        circuit_failure_threshold: int = 3,
        circuit_cooldown_sec: float = 30.0,
    ) -> None:
        self._client = client
        self._session_id = session_id
        self._bus: EventBus | None = None
        self._request_lock = asyncio.Lock()
        self._circuit_failure_threshold = circuit_failure_threshold
        self._circuit_cooldown_sec = circuit_cooldown_sec
        self._consecutive_failures = 0
        self._circuit_state: Literal["closed", "open", "half_open"] = "closed"
        self._opened_at: float | None = None
        self._half_open_probe_in_flight = False

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
        await self._refresh_circuit_state()
        if self._circuit_state == "open" or (
            self._circuit_state == "half_open" and self._half_open_probe_in_flight
        ):
            await self._publish(
                "cognition.unavailable",
                {"reason": "circuit_open", "correlation_id": event.correlation_id},
                event,
            )
            return
        is_half_open_probe = self._circuit_state == "half_open"
        if is_half_open_probe:
            self._half_open_probe_in_flight = True
        try:
            async with self._request_lock:
                response = await self._client.request(payload)
            self._consecutive_failures = 0
            if is_half_open_probe:
                await self._set_circuit_state("closed")
            response = {**response, "correlation_id": event.correlation_id}
            await self._publish("cognition.response_received", response, event)
        except Exception as exc:
            self._consecutive_failures += 1
            if (
                self._circuit_state == "half_open"
                or self._consecutive_failures >= self._circuit_failure_threshold
            ):
                await self._set_circuit_state("open")
            await self._publish(
                "cognition.unavailable",
                {"reason": str(exc), "correlation_id": event.correlation_id},
                event,
            )
        finally:
            if is_half_open_probe:
                self._half_open_probe_in_flight = False

    async def _refresh_circuit_state(self) -> None:
        if self._circuit_state != "open" or self._opened_at is None:
            return
        if time.monotonic() - self._opened_at >= self._circuit_cooldown_sec:
            await self._set_circuit_state("half_open")

    async def _set_circuit_state(
        self,
        state: Literal["closed", "open", "half_open"],
    ) -> None:
        if self._circuit_state == state:
            if state == "open":
                self._opened_at = time.monotonic()
            return
        self._circuit_state = state
        if state == "closed":
            self._opened_at = None
            self._half_open_probe_in_flight = False
            self._consecutive_failures = 0
            await self._publish_health("healthy")
        elif state == "half_open":
            await self._publish_health("degraded")
        else:
            self._opened_at = time.monotonic()
            self._half_open_probe_in_flight = False
            await self._publish_health("unavailable")

    async def _publish_health(self, status: str) -> None:
        if self._bus is None:
            return
        await self._bus.publish(
            Event(
                event_type="system.health_changed",
                source="cognition_bridge",
                session_id=self._session_id,
                payload={"component": "cognition", "status": status, "kind": "bridge"},
            )
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
