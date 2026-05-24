from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from roamerd.contracts.action import ActionStatus, PreemptionScope
from roamerd.contracts.errors import ErrorCode
from roamerd.events import Event, Priority
from roamerd.kernel.event_bus import EventBus
from roamerd.types import JSONDict

__all__ = [
    "Action",
    "ActionManager",
    "ActionRequestError",
    "ActionStatus",
    "PreemptionScope",
]


class ActionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Action(ActionModel):
    action_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    action_type: str
    resource: str = "none"
    priority: Priority = Priority.NORMAL
    status: ActionStatus = ActionStatus.PENDING
    source_module: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    waiting_for_action_id: str | None = None
    waiting_deadline: datetime | None = None
    turn_id: str | None = None
    payload: JSONDict = Field(default_factory=dict)
    result: JSONDict | None = None
    error: JSONDict | None = None


class ActionRequestError(ActionModel):
    ok: bool = False
    error_code: ErrorCode
    message: str
    resource: str | None = None
    action_id: str | None = None


class ActionManager:
    def __init__(
        self,
        *,
        session_id: str = "session-1",
        preemption_timeout_sec: float = 5.0,
    ) -> None:
        self._bus: EventBus | None = None
        self._session_id = session_id
        self._actions: dict[str, Action] = {}
        self._resource_locks: dict[str, str] = {}
        self._preemption_timeout_sec = preemption_timeout_sec
        self._waiting_by_blocker: dict[str, str] = {}
        self._timeout_tasks: dict[str, asyncio.Task[None]] = {}

    async def start(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe("system.health_changed", self._handle_health_changed)

    async def request_action(
        self,
        action_type: str,
        payload: JSONDict,
        *,
        resource: str = "none",
        priority: Priority = Priority.NORMAL,
        turn_id: str | None = None,
        source_module: str | None = None,
        preempt_current: bool = False,
    ) -> Action | ActionRequestError:
        if resource != "none" and self._resource_is_occupied(resource):
            if preempt_current:
                current_id = self._resource_locks[resource]
                return await self._request_waiting_action(
                    current_id,
                    action_type,
                    payload,
                    resource=resource,
                    priority=priority,
                    turn_id=turn_id,
                    source_module=source_module,
                )
            return ActionRequestError(
                error_code=ErrorCode.BUSY,
                message=f"resource busy: {resource}",
                resource=resource,
                action_id=self._resource_locks.get(resource),
            )
        action = Action(
            action_type=action_type,
            payload=payload,
            resource=resource,
            priority=priority,
            turn_id=turn_id,
            source_module=source_module,
            status=ActionStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        self._actions[action.action_id] = action
        if resource != "none":
            self._resource_locks[resource] = action.action_id
        await self._publish_action_started(action)
        return action

    async def complete_action(self, action_id: str, result: JSONDict) -> None:
        action = self._actions[action_id]
        self._cancel_timeout(action_id)
        action.status = ActionStatus.COMPLETED
        action.result = result
        action.completed_at = datetime.now(UTC)
        self._release_resource(action)
        await self._publish(
            "action.completed",
            action,
            {"action_id": action.action_id, "result": result},
        )
        await self._start_waiting_after(action.action_id)

    async def fail_action(self, action_id: str, error: JSONDict) -> None:
        action = self._actions[action_id]
        self._cancel_timeout(action_id)
        action.status = ActionStatus.FAILED
        action.error = error
        action.completed_at = datetime.now(UTC)
        self._release_resource(action)
        await self._publish(
            "action.failed",
            action,
            {"action_id": action.action_id, "error": error},
        )
        await self._start_waiting_after(action.action_id)

    async def cancel_action(self, action_id: str, reason: str) -> None:
        action = self._actions[action_id]
        await self._publish(
            "action.cancel_requested",
            action,
            {"action_id": action.action_id, "reason": reason},
        )
        self._timeout_tasks[action_id] = asyncio.create_task(self._cancel_after_timeout(action_id))

    async def mark_cancelled(self, action_id: str, reason: str) -> None:
        action = self._actions[action_id]
        self._cancel_timeout(action_id)
        action.status = ActionStatus.CANCELLED
        action.completed_at = datetime.now(UTC)
        self._release_resource(action)
        await self._publish(
            "action.cancelled",
            action,
            {"action_id": action.action_id, "reason": reason},
        )
        await self._start_waiting_after(action.action_id)

    async def preempt(self, scope: PreemptionScope) -> list[str]:
        preempted: list[str] = []
        for action in self._actions.values():
            if action.resource not in scope.target_resources:
                continue
            if action.status not in {ActionStatus.RUNNING, ActionStatus.RUNNING_DETACHED}:
                continue
            action.status = ActionStatus.PREEMPTING
            preempted.append(action.action_id)
            await self._publish(
                "action.preempt_requested",
                action,
                {"action_id": action.action_id, "reason": scope.reason},
            )
            self._timeout_tasks[action.action_id] = asyncio.create_task(
                self._preempt_after_timeout(action.action_id)
            )
        return preempted

    async def mark_preempted(self, action_id: str, reason: str) -> None:
        action = self._actions[action_id]
        self._cancel_timeout(action_id)
        action.status = ActionStatus.PREEMPTED
        action.completed_at = datetime.now(UTC)
        self._release_resource(action)
        await self._publish(
            "action.preempted",
            action,
            {"action_id": action.action_id, "reason": reason},
        )
        await self._start_waiting_after(action.action_id)

    async def mark_detached(self, action_id: str, reason: str = "client_timeout") -> None:
        action = self._actions[action_id]
        action.status = ActionStatus.RUNNING_DETACHED
        await self._publish(
            "action.detached",
            action,
            {"action_id": action.action_id, "reason": reason},
        )

    async def _handle_health_changed(self, event: Event) -> None:
        component = event.payload.get("component")
        status = event.payload.get("status")
        if not isinstance(component, str) or status != "unavailable":
            return
        action_ids = [
            action.action_id
            for action in self.get_running_actions()
            if action.source_module == component
        ]
        for action_id in action_ids:
            await self.fail_action(action_id, {"reason": "module_crashed"})

    def get_action(self, action_id: str) -> Action | None:
        return self._actions.get(action_id)

    def get_running_actions(self, resource: str | None = None) -> list[Action]:
        active_statuses = {
            ActionStatus.RUNNING,
            ActionStatus.RUNNING_DETACHED,
            ActionStatus.PREEMPTING,
        }
        return [
            action
            for action in self._actions.values()
            if action.status in active_statuses
            and (resource is None or action.resource == resource)
        ]

    def _resource_is_occupied(self, resource: str) -> bool:
        action_id = self._resource_locks.get(resource)
        if action_id is None:
            return False
        action = self._actions[action_id]
        return action.status in {
            ActionStatus.RUNNING,
            ActionStatus.RUNNING_DETACHED,
            ActionStatus.PREEMPTING,
        }

    def _release_resource(self, action: Action) -> None:
        if (
            action.resource != "none"
            and self._resource_locks.get(action.resource) == action.action_id
        ):
            self._resource_locks.pop(action.resource)

    async def _request_waiting_action(
        self,
        current_id: str,
        action_type: str,
        payload: JSONDict,
        *,
        resource: str,
        priority: Priority,
        turn_id: str | None,
        source_module: str | None,
    ) -> Action | ActionRequestError:
        current = self._actions[current_id]
        if current.status is ActionStatus.PREEMPTING:
            return ActionRequestError(
                error_code=ErrorCode.BUSY,
                message=f"resource already preempting: {resource}",
                resource=resource,
                action_id=current_id,
            )
        current.status = ActionStatus.PREEMPTING
        now = datetime.now(UTC)
        action = Action(
            action_type=action_type,
            payload=payload,
            resource=resource,
            priority=priority,
            turn_id=turn_id,
            source_module=source_module,
            status=ActionStatus.WAITING_RESOURCE,
            waiting_for_action_id=current_id,
            waiting_deadline=now + timedelta(seconds=self._preemption_timeout_sec),
        )
        self._actions[action.action_id] = action
        self._waiting_by_blocker[current_id] = action.action_id
        await self._publish(
            "action.preempt_requested",
            current,
            {"action_id": current.action_id, "reason": "preempt_current"},
        )
        self._timeout_tasks[action.action_id] = asyncio.create_task(
            self._fail_waiting_action_after_timeout(action.action_id, current_id)
        )
        return action

    async def _fail_waiting_action_after_timeout(
        self,
        action_id: str,
        waiting_for_action_id: str,
    ) -> None:
        await asyncio.sleep(self._preemption_timeout_sec)
        self._timeout_tasks.pop(action_id, None)
        action = self._actions.get(action_id)
        if action is None or action.status is not ActionStatus.WAITING_RESOURCE:
            return
        action.status = ActionStatus.FAILED
        action.completed_at = datetime.now(UTC)
        action.error = {
            "reason": "resource_preemption_timeout",
            "waiting_for_action_id": waiting_for_action_id,
        }
        self._waiting_by_blocker.pop(waiting_for_action_id, None)
        await self._publish(
            "action.failed",
            action,
            {"action_id": action.action_id, "error": action.error},
        )

    async def _cancel_after_timeout(self, action_id: str) -> None:
        await asyncio.sleep(self._preemption_timeout_sec)
        self._timeout_tasks.pop(action_id, None)
        action = self._actions.get(action_id)
        if action is None or action.status not in {
            ActionStatus.RUNNING,
            ActionStatus.RUNNING_DETACHED,
            ActionStatus.PREEMPTING,
        }:
            return
        action.status = ActionStatus.CANCELLED
        action.completed_at = datetime.now(UTC)
        self._release_resource(action)
        await self._publish(
            "action.cancelled",
            action,
            {"action_id": action.action_id, "reason": "cancel_timeout"},
        )
        await self._start_waiting_after(action.action_id)

    async def _preempt_after_timeout(self, action_id: str) -> None:
        await asyncio.sleep(self._preemption_timeout_sec)
        self._timeout_tasks.pop(action_id, None)
        action = self._actions.get(action_id)
        if action is None or action.status is not ActionStatus.PREEMPTING:
            return
        action.status = ActionStatus.PREEMPTED
        action.completed_at = datetime.now(UTC)
        self._release_resource(action)
        await self._publish(
            "action.preempted",
            action,
            {"action_id": action.action_id, "reason": "preempt_timeout"},
        )
        await self._start_waiting_after(action.action_id)

    async def _start_waiting_after(self, blocker_action_id: str) -> None:
        waiting_action_id = self._waiting_by_blocker.pop(blocker_action_id, None)
        if waiting_action_id is None:
            return
        action = self._actions[waiting_action_id]
        if action.status is not ActionStatus.WAITING_RESOURCE:
            return
        timeout_task = self._timeout_tasks.pop(waiting_action_id, None)
        if timeout_task is not None:
            timeout_task.cancel()
        if action.resource != "none" and action.resource in self._resource_locks:
            action.status = ActionStatus.FAILED
            action.error = {"reason": "resource_busy_after_preemption"}
            action.completed_at = datetime.now(UTC)
            await self._publish(
                "action.failed",
                action,
                {"action_id": action.action_id, "error": action.error},
            )
            return
        action.status = ActionStatus.RUNNING
        action.started_at = datetime.now(UTC)
        if action.resource != "none":
            self._resource_locks[action.resource] = action.action_id
        await self._publish_action_started(action)

    def _cancel_timeout(self, action_id: str) -> None:
        task = self._timeout_tasks.pop(action_id, None)
        if task is None or task is asyncio.current_task():
            return
        task.cancel()

    async def _publish_action_started(self, action: Action) -> None:
        await self._publish(
            "action.started",
            action,
            {
                "action_id": action.action_id,
                "action_type": action.action_type,
                "resource": action.resource,
            },
        )

    async def _publish(self, event_type: str, action: Action, payload: JSONDict) -> None:
        if self._bus is None:
            return
        await self._bus.publish(
            Event(
                event_type=event_type,
                source="action_manager",
                session_id=self._session_id,
                action_id=action.action_id,
                turn_id=action.turn_id,
                priority=action.priority,
                payload=payload,
            )
        )
