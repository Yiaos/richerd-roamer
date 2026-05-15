"""Body status action module."""

from __future__ import annotations

from roamerd.capabilities.body_status import BodyStatus
from roamerd.events.base import Event, make_event
from roamerd.kernel.action_manager import ActionManager
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.state_manager import HealthState


class BodyStatusModule:
    name = "body_status"
    resource = "none"
    events_produced = ["body.status_ready"]
    events_consumed = ["action.started"]

    def __init__(self, *, session_id: str, action_manager: ActionManager) -> None:
        self._session_id = session_id
        self._actions = action_manager
        self._status = BodyStatus()
        self._bus: EventBus | None = None

    async def start(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe("action.started", self._on_action_started)
        await bus.publish(
            make_event(
                "system.module_ready",
                source="body_status_module",
                session_id=self._session_id,
                payload={"name": self.name, "component_type": "module", "state": "healthy"},
            )
        )

    async def stop(self) -> None:
        return None

    async def health_check(self) -> HealthState:
        return HealthState.HEALTHY

    async def _on_action_started(self, event: Event) -> None:
        if event.payload.get("action_type") != "sense" or self._bus is None:
            return
        payload = event.payload.get("payload")
        args = payload if isinstance(payload, dict) else {}
        result = self._status.snapshot(full=bool(args.get("full", False)))
        action_id = event.action_id or ""
        await self._bus.publish(
            make_event(
                "body.status_ready",
                source="body_status_module",
                session_id=self._session_id,
                action_id=action_id,
                payload=result,
            )
        )
        await self._actions.complete_action(action_id, result)
