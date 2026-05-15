"""In-process control bridge helpers."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from roamerd.events.base import Event, JSONDict, Priority, make_event
from roamerd.events.control import ControlCommandPayload, WaitMode
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.state_manager import HealthState


class ControlBridge:
    name = "control"

    def __init__(self, *, session_id: str) -> None:
        self._session_id = session_id
        self._bus: EventBus | None = None
        self._pending: dict[str, asyncio.Future[JSONDict]] = {}
        self._pending_actions: dict[str, asyncio.Future[JSONDict]] = {}
        self._terminal_actions: dict[str, JSONDict] = {}
        self._health = HealthState.HEALTHY
        self._unavailable_reason: str | None = None

    async def start(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe("control.response_ready", self._on_response)
        for event_type in (
            "action.completed",
            "action.failed",
            "action.cancelled",
            "action.preempted",
        ):
            bus.subscribe(event_type, self._on_action_terminal)
        await bus.publish(
            make_event(
                "system.module_ready",
                source="control_bridge",
                session_id=self._session_id,
                payload={
                    "name": self.name,
                    "component_type": "bridge",
                    "state": self._health.value,
                    "reason": self._unavailable_reason,
                },
            )
        )

    async def stop(self) -> None:
        for future in self._pending.values():
            if not future.done():
                future.cancel()

    async def health_check(self) -> HealthState:
        return self._health

    def mark_unavailable(self, reason: str) -> None:
        self._health = HealthState.UNAVAILABLE
        self._unavailable_reason = reason

    async def request(self, command: ControlCommandPayload) -> JSONDict:
        if self._bus is None:
            return {
                "ok": False,
                "error_code": "control.unavailable",
                "error_message": "control bridge not started",
            }
        future: asyncio.Future[JSONDict] = asyncio.get_running_loop().create_future()
        self._pending[command.correlation_id] = future
        await self._bus.publish(
            make_event(
                "control.command_received",
                source="control_bridge",
                session_id=self._session_id,
                payload=command.model_dump(mode="json"),
                correlation_id=command.correlation_id,
                priority=Priority.HIGH,
            )
        )
        accepted = await asyncio.wait_for(future, timeout=command.timeout_ms / 1000)
        if command.wait == WaitMode.ACCEPTED or command.op != "run":
            response = self._response_with_command_ids(command, accepted)
            await self._publish_response_sent(command, response)
            return response
        action_id = _extract_action_id(accepted)
        if action_id is None or not bool(accepted.get("ok", False)):
            response = self._response_with_command_ids(command, accepted)
            await self._publish_response_sent(command, response)
            return response
        terminal = self._terminal_actions.pop(action_id, None)
        if terminal is not None:
            response = self._response_with_command_ids(command, terminal)
            await self._publish_response_sent(command, response)
            return response
        action_future: asyncio.Future[JSONDict] = asyncio.get_running_loop().create_future()
        self._pending_actions[action_id] = action_future
        try:
            response = await asyncio.wait_for(action_future, timeout=command.timeout_ms / 1000)
        except TimeoutError:
            response = {
                "ok": False,
                "error_code": "client.timeout",
                "error_message": "action did not complete before client timeout",
                "action_id": action_id,
            }
        response = self._response_with_command_ids(command, response)
        await self._publish_response_sent(command, response)
        return response

    async def run(self, action: str, args: JSONDict | None = None) -> JSONDict:
        return await self.request(
            ControlCommandPayload(
                op="run",
                action=action,
                args=args or {},
                correlation_id=uuid4().hex[:12],
            )
        )

    async def query(self, target: str) -> JSONDict:
        return await self.request(
            ControlCommandPayload(
                op="query",
                target=target,
                correlation_id=uuid4().hex[:12],
            )
        )

    async def _on_response(self, event: object) -> None:
        from roamerd.events.base import Event

        if not isinstance(event, Event):
            return
        correlation_id = str(event.payload.get("correlation_id", event.correlation_id or ""))
        future = self._pending.pop(correlation_id, None)
        if future is not None and not future.done():
            future.set_result(event.payload)

    async def _on_action_terminal(self, event: object) -> None:
        from roamerd.events.base import Event

        if not isinstance(event, Event) or event.action_id is None:
            return
        future = self._pending_actions.pop(event.action_id, None)
        terminal = _terminal_response(event)
        if future is None or future.done():
            self._terminal_actions[event.action_id] = terminal
            return
        future.set_result(terminal)

    async def _publish_response_sent(
        self, command: ControlCommandPayload, response: JSONDict
    ) -> None:
        if self._bus is None:
            return
        payload = self._response_with_command_ids(command, response)
        await self._bus.publish(
            make_event(
                "control.response_sent",
                source="control_bridge",
                session_id=self._session_id,
                payload=payload,
                correlation_id=command.correlation_id,
                priority=Priority.HIGH,
            )
        )

    def _response_with_command_ids(
        self, command: ControlCommandPayload, response: JSONDict
    ) -> JSONDict:
        payload = dict(response)
        payload.setdefault("correlation_id", command.correlation_id)
        if command.request_id is not None:
            payload.setdefault("request_id", command.request_id)
        if command.trace_id is not None:
            payload.setdefault("trace_id", command.trace_id)
        return payload


def _extract_action_id(response: JSONDict) -> str | None:
    raw_result = response.get("result")
    if not isinstance(raw_result, dict):
        return None
    action_id = raw_result.get("action_id")
    return str(action_id) if action_id else None


def _terminal_response(event: Event) -> JSONDict:
    ok = event.event_type == "action.completed"
    return {
        "ok": ok,
        "action_id": event.action_id,
        "state": event.event_type.removeprefix("action."),
        "result": event.payload.get("result", event.payload),
        "error_code": None if ok else "action.failed",
    }
