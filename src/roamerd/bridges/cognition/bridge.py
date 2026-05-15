"""Cognition bridge: text pipe to an external or mock cognition adapter."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from roamerd.events.base import Event, make_event
from roamerd.events.cognition import CognitionResponsePayload, CognitionResponseType
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.state_manager import HealthState


@runtime_checkable
class CognitionAdapter(Protocol):
    async def request(
        self, text: str, *, turn_id: str, correlation_id: str
    ) -> CognitionResponsePayload: ...

    async def health_check(self) -> HealthState: ...


class CognitionBridge:
    name = "cognition"

    def __init__(
        self, *, session_id: str, adapter: CognitionAdapter, failure_threshold: int = 3
    ) -> None:
        self._session_id = session_id
        self._adapter = adapter
        self._failure_threshold = max(failure_threshold, 1)
        self._consecutive_failures = 0
        self._health = HealthState.HEALTHY
        self._unavailable_reason: str | None = None
        self._bus: EventBus | None = None

    async def start(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe("cognition.request_needed", self._on_request)
        await bus.publish(
            make_event(
                "system.module_ready",
                source="cognition_bridge",
                session_id=self._session_id,
                payload={"name": self.name, "component_type": "bridge", "state": "healthy"},
            )
        )

    async def stop(self) -> None:
        return None

    async def health_check(self) -> HealthState:
        if self._health != HealthState.HEALTHY:
            return self._health
        return await self._adapter.health_check()

    async def _on_request(self, event: Event) -> None:
        if self._bus is None:
            return
        try:
            response = await self._adapter.request(
                str(event.payload.get("text", "")),
                turn_id=str(event.payload.get("turn_id", event.turn_id or "")),
                correlation_id=str(event.payload.get("correlation_id", event.correlation_id or "")),
            )
        except Exception as exc:
            self._consecutive_failures += 1
            reason = exc.__class__.__name__
            self._unavailable_reason = reason
            if self._consecutive_failures >= self._failure_threshold:
                await self._set_health(HealthState.DEGRADED, reason=reason)
            await self._bus.publish(
                make_event(
                    "cognition.unavailable",
                    source="cognition_bridge",
                    session_id=self._session_id,
                    payload={
                        "reason": reason,
                        "consecutive_failures": self._consecutive_failures,
                    },
                    correlation_id=event.correlation_id,
                )
            )
            return
        self._consecutive_failures = 0
        self._unavailable_reason = None
        if self._health != HealthState.HEALTHY:
            await self._set_health(HealthState.HEALTHY, reason=None)
        await self._bus.publish(
            make_event(
                "cognition.response_received",
                source="cognition_bridge",
                session_id=self._session_id,
                payload=response.model_dump(mode="json"),
                correlation_id=response.correlation_id,
                turn_id=event.turn_id,
            )
        )

    async def _set_health(self, health: HealthState, *, reason: str | None) -> None:
        if self._bus is None or self._health == health:
            self._health = health
            return
        self._health = health
        await self._bus.publish(
            make_event(
                "system.health_changed",
                source="cognition_bridge",
                session_id=self._session_id,
                payload={
                    "name": self.name,
                    "component_type": "bridge",
                    "state": health.value,
                    "reason": reason,
                },
            )
        )


class MockCognitionAdapter:
    def __init__(self, response_text: str = "我听到了。") -> None:
        self.response_text = response_text

    async def request(
        self, text: str, *, turn_id: str, correlation_id: str
    ) -> CognitionResponsePayload:
        return CognitionResponsePayload(
            correlation_id=correlation_id,
            response_type=CognitionResponseType.SPEAK,
            text=self.response_text,
            latency_ms=0,
        )

    async def health_check(self) -> HealthState:
        return HealthState.HEALTHY
