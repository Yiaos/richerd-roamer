"""Action lifecycle and resource lock manager."""

from __future__ import annotations

from datetime import datetime, timezone

from roamerd.contracts.action import Action, ActionStatus, PreemptionScope
from roamerd.contracts.exceptions import ResourceBusyError
from roamerd.events.base import Event, JSONDict, Priority, make_event
from roamerd.kernel.event_bus import EventBus


class ActionManager:
    def __init__(self, *, session_id: str) -> None:
        self._session_id = session_id
        self._bus: EventBus | None = None
        self._actions: dict[str, Action] = {}
        self._resource_locks: dict[str, str] = {}

    async def start(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe("system.health_changed", self._on_health_changed)

    async def request_action(
        self,
        action_type: str,
        payload: JSONDict,
        *,
        resource: str = "none",
        priority: Priority = Priority.NORMAL,
        turn_id: str | None = None,
    ) -> Action:
        if resource != "none" and resource in self._resource_locks:
            raise ResourceBusyError(f"resource busy: {resource}")
        action = Action(
            action_type=action_type,
            resource=resource,
            priority=priority,
            payload=payload,
            turn_id=turn_id,
        )
        action.status = ActionStatus.RUNNING
        action.started_at = datetime.now(timezone.utc)
        self._actions[action.action_id] = action
        if resource != "none":
            self._resource_locks[resource] = action.action_id
        await self._publish(
            "action.started",
            action,
            {
                "action_type": action.action_type,
                "resource": action.resource,
                "priority": action.priority.wire_value,
                "payload": action.payload,
            },
            priority=priority,
        )
        return action

    async def complete_action(self, action_id: str, result: JSONDict) -> None:
        action = self._require_action(action_id)
        action.status = ActionStatus.COMPLETED
        action.completed_at = datetime.now(timezone.utc)
        action.result = result
        self._release(action)
        await self._publish("action.completed", action, {"result": result})

    async def fail_action(self, action_id: str, error: JSONDict) -> None:
        action = self._require_action(action_id)
        action.status = ActionStatus.FAILED
        action.completed_at = datetime.now(timezone.utc)
        action.error = error
        self._release(action)
        await self._publish("action.failed", action, {"error": error})

    async def cancel_action(self, action_id: str, reason: str) -> None:
        action = self._require_action(action_id)
        action.status = ActionStatus.CANCELLED
        action.completed_at = datetime.now(timezone.utc)
        self._release(action)
        await self._publish(
            "action.cancelled",
            action,
            {**_action_metadata(action), "reason": reason},
            priority=Priority.HIGH,
        )

    async def preempt(self, scope: PreemptionScope) -> list[str]:
        preempted: list[str] = []
        for resource in scope.target_resources:
            action_id = self._resource_locks.get(resource)
            if action_id is None:
                continue
            action = self._actions[action_id]
            action.status = ActionStatus.PREEMPTED
            action.completed_at = datetime.now(timezone.utc)
            self._release(action)
            preempted.append(action.action_id)
            await self._publish(
                "action.preempted",
                action,
                {
                    **_action_metadata(action),
                    "reason": scope.reason,
                    "source_event": scope.source_event,
                },
                priority=Priority.CRITICAL,
            )
        return preempted

    def get_action(self, action_id: str) -> Action | None:
        action = self._actions.get(action_id)
        return action.model_copy(deep=True) if action is not None else None

    def get_running_actions(self, resource: str | None = None) -> list[Action]:
        actions = [
            action
            for action in self._actions.values()
            if action.status == ActionStatus.RUNNING
            and (resource is None or action.resource == resource)
        ]
        return [action.model_copy(deep=True) for action in actions]

    def list_actions(self) -> list[Action]:
        return [action.model_copy(deep=True) for action in self._actions.values()]

    async def _on_health_changed(self, event: Event) -> None:
        if event.payload.get("component_type", "module") != "module":
            return
        if event.payload.get("state") != "unavailable":
            return
        resource = str(event.payload.get("name", ""))
        action_id = self._resource_locks.get(resource)
        if action_id is None:
            return
        await self.fail_action(
            action_id,
            {
                "error_code": "module_crashed",
                "error_message": f"{resource} module unavailable",
            },
        )

    async def _publish(
        self,
        event_type: str,
        action: Action,
        payload: JSONDict,
        *,
        priority: Priority = Priority.NORMAL,
    ) -> None:
        if self._bus is None:
            return
        await self._bus.publish(
            make_event(
                event_type,
                source="action_manager",
                session_id=self._session_id,
                payload=payload,
                action_id=action.action_id,
                turn_id=action.turn_id,
                priority=priority,
            )
        )

    def _require_action(self, action_id: str) -> Action:
        action = self._actions.get(action_id)
        if action is None:
            raise KeyError(action_id)
        return action

    def _release(self, action: Action) -> None:
        if (
            action.resource != "none"
            and self._resource_locks.get(action.resource) == action.action_id
        ):
            del self._resource_locks[action.resource]


def _action_metadata(action: Action) -> JSONDict:
    return {
        "action_type": action.action_type,
        "resource": action.resource,
        "priority": action.priority.wire_value,
        "payload": action.payload,
    }
