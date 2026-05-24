from __future__ import annotations

import asyncio
from typing import Protocol

from roamerd.bridges.control.protocol import RequestEnvelope, ResponseEnvelope
from roamerd.bridges.control.session import SessionCoordinator
from roamerd.contracts.action import ActionStatus
from roamerd.events import Event
from roamerd.kernel import ActionManager, ActionRequest, PolicyEngine, StateManager
from roamerd.kernel.event_bus import EventBus
from roamerd.types import JSONDict


class Router(Protocol):
    async def dispatch(self, request: RequestEnvelope) -> ResponseEnvelope: ...


class StaticRouter:
    def __init__(self, result: JSONDict) -> None:
        self._result = result

    async def dispatch(self, request: RequestEnvelope) -> ResponseEnvelope:
        return ResponseEnvelope(
            request_id=request.request_id,
            trace_id=request.trace_id,
            status="ok",
            op=request.op,
            result=self._result,
        )


class ControlCommandRouter:
    def __init__(
        self,
        *,
        event_bus: EventBus,
        action_manager: ActionManager,
        policy_engine: PolicyEngine,
        state_manager: StateManager,
    ) -> None:
        self._bus = event_bus
        self._actions = action_manager
        self._policy = policy_engine
        self._state = state_manager
        self._sessions = SessionCoordinator()

    async def dispatch(self, request: RequestEnvelope) -> ResponseEnvelope:
        if request.op == "ping":
            return self._ok(request, {"pong": True})
        if request.op == "status":
            return self._ok(request, self._state.snapshot().model_dump(mode="json"))
        if request.op == "run":
            return await self._run(request)
        if request.op == "session.start":
            session = self._sessions.start(str(request.args.get("kind", "voice_turn")))
            return self._ok(request, {"session_id": session.session_id, "kind": session.kind})
        if request.op == "action.status":
            return self._action_status(request)
        if request.op == "action.cancel":
            return await self._action_cancel(request)
        if request.op == "actions.list":
            return self._actions_list(request)
        return ResponseEnvelope(
            request_id=request.request_id,
            trace_id=request.trace_id,
            status="error",
            op=request.op,
            error={"code": "UNKNOWN_OP", "message": request.op},
        )

    async def _run(self, request: RequestEnvelope) -> ResponseEnvelope:
        action_type = str(request.args.get("action", ""))
        payload = request.args.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}
        decision = await self._policy.admit_action(
            ActionRequest(
                action_type=action_type,
                payload=payload,
                resource=str(request.args.get("resource", "none")),
                source="control_bridge",
            )
        )
        if not decision.admitted:
            return ResponseEnvelope(
                request_id=request.request_id,
                trace_id=request.trace_id,
                status="error",
                op=request.op,
                error={"code": "REJECTED", "message": decision.reason},
            )
        if decision.action_id is None or request.wait == "accepted":
            return ResponseEnvelope(
                request_id=request.request_id,
                trace_id=request.trace_id,
                status="ok",
                op=request.op,
                action_id=decision.action_id,
                result={"accepted": True},
            )
        return await self._wait_for_completed_action(request, decision.action_id)

    async def _wait_for_completed_action(
        self,
        request: RequestEnvelope,
        action_id: str,
    ) -> ResponseEnvelope:
        future: asyncio.Future[Event] = asyncio.get_running_loop().create_future()

        async def handler(event: Event) -> None:
            if event.action_id != action_id and event.payload.get("action_id") != action_id:
                return
            if not future.done():
                future.set_result(event)

        subscriptions = [
            self._bus.subscribe("action.completed", handler),
            self._bus.subscribe("action.failed", handler),
            self._bus.subscribe("action.cancelled", handler),
            self._bus.subscribe("action.preempted", handler),
        ]
        try:
            event = await asyncio.wait_for(future, timeout=request.timeout_ms / 1000)
        except TimeoutError:
            action = self._actions.get_action(action_id)
            if action is not None and action.status in {
                ActionStatus.RUNNING,
                ActionStatus.PREEMPTING,
                ActionStatus.WAITING_RESOURCE,
            }:
                await self._actions.mark_detached(action_id, "control_bridge_wait_timeout")
            return ResponseEnvelope(
                request_id=request.request_id,
                trace_id=request.trace_id,
                status="error",
                op=request.op,
                action_id=action_id,
                error={"code": "TIMEOUT", "message": "action completion timed out"},
            )
        finally:
            for subscription in subscriptions:
                self._bus.unsubscribe(subscription.id)

        action = self._actions.get_action(action_id)
        if event.event_type == "action.completed":
            result = action.result if action is not None and action.result is not None else {}
            return self._ok(request, result, action_id=action_id)
        return ResponseEnvelope(
            request_id=request.request_id,
            trace_id=request.trace_id,
            status="error",
            op=request.op,
            action_id=action_id,
            error={
                "code": str(event.payload.get("error", event.event_type)).upper(),
                "message": event.event_type,
            },
        )

    def _action_status(self, request: RequestEnvelope) -> ResponseEnvelope:
        action = self._actions.get_action(str(request.args.get("action_id", "")))
        if action is None:
            return ResponseEnvelope(
                request_id=request.request_id,
                trace_id=request.trace_id,
                status="error",
                op=request.op,
                error={"code": "ACTION_NOT_FOUND"},
            )
        return self._ok(request, action.model_dump(mode="json"), action_id=action.action_id)

    async def _action_cancel(self, request: RequestEnvelope) -> ResponseEnvelope:
        action = self._actions.get_action(str(request.args.get("action_id", "")))
        if action is None:
            return ResponseEnvelope(
                request_id=request.request_id,
                trace_id=request.trace_id,
                status="error",
                op=request.op,
                error={"code": "ACTION_NOT_FOUND"},
            )
        await self._actions.cancel_action(action.action_id, "control_bridge")
        return self._ok(
            request,
            {"cancel_requested": True},
            action_id=action.action_id,
        )

    def _actions_list(self, request: RequestEnvelope) -> ResponseEnvelope:
        return self._ok(
            request,
            {
                "actions": [
                    action.model_dump(mode="json")
                    for action in self._actions.get_running_actions()
                ]
            },
        )

    def _ok(
        self,
        request: RequestEnvelope,
        result: JSONDict,
        *,
        action_id: str | None = None,
    ) -> ResponseEnvelope:
        return ResponseEnvelope(
            request_id=request.request_id,
            trace_id=request.trace_id,
            status="ok",
            op=request.op,
            action_id=action_id,
            result=result,
        )
