from __future__ import annotations

import socket
import time
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from roamerd.events import Event
from roamerd.kernel import ActionManager, EventBus
from roamerd.types import JSONDict


class BodyStatusSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hostname: str
    uptime_sec: float
    cpu_percent: float
    memory_used_mb: int
    memory_total_mb: int
    temperature_c: float | None = None
    disk_used_mb: int
    disk_total_mb: int
    network_interfaces: list[str]
    hardware_checks: dict[str, str] = Field(default_factory=dict)


class BodyStatusProvider(Protocol):
    async def snapshot(self) -> BodyStatusSnapshot: ...


class LocalBodyStatusProvider:
    async def snapshot(self) -> BodyStatusSnapshot:
        return BodyStatusSnapshot(
            hostname=socket.gethostname(),
            uptime_sec=time.monotonic(),
            cpu_percent=0.0,
            memory_used_mb=0,
            memory_total_mb=0,
            temperature_c=None,
            disk_used_mb=0,
            disk_total_mb=0,
            network_interfaces=[],
            hardware_checks={
                "alsa": "unknown",
                "bluetooth": "unknown",
                "camera": "unknown",
                "tailscale": "unknown",
            },
        )


class BodyStatusModule:
    name = "body"
    events_produced = ["system.health_changed"]
    events_consumed = ["action.started"]
    resources = ["none"]

    def __init__(
        self,
        *,
        provider: BodyStatusProvider,
        action_manager: ActionManager | None = None,
        session_id: str = "session-1",
    ) -> None:
        self._provider = provider
        self._actions = action_manager
        self._session_id = session_id
        self._bus: EventBus | None = None

    async def start(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe("action.started", self._handle_action_started)

    async def stop(self) -> None:
        return None

    async def health_check(self) -> str:
        return "healthy"

    async def _handle_action_started(self, event: Event) -> None:
        if event.payload.get("action_type") not in {"sense", "body.status"}:
            return
        action_id = event.action_id or str(event.payload.get("action_id", ""))
        snapshot = await self._provider.snapshot()
        await self._publish_health("healthy")
        if self._actions is not None:
            await self._actions.complete_action(action_id, snapshot.model_dump(mode="json"))

    async def _publish_health(self, status: str) -> None:
        if self._bus is None:
            return
        payload: JSONDict = {"component": "body", "status": status}
        await self._bus.publish(
            Event(
                event_type="system.health_changed",
                source="body",
                session_id=self._session_id,
                payload=payload,
            )
        )
