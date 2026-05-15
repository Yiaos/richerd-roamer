"""Non-persistent reminder capability."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from roamerd.events.base import Event, Priority, make_event
from roamerd.kernel.action_manager import ActionManager
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.state_manager import HealthState


class ReminderScheduler:
    def __init__(self, speak: Callable[[str], Awaitable[None]]) -> None:
        self._speak = speak
        self._tasks: list[asyncio.Task[None]] = []

    def schedule(self, *, delay_sec: float, text: str) -> None:
        self._tasks.append(asyncio.create_task(self._run(delay_sec, text)))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _run(self, delay_sec: float, text: str) -> None:
        await asyncio.sleep(delay_sec)
        await self._speak(text)


class ReminderModule:
    name = "reminder"
    resource = "none"
    events_produced = ["reminder.scheduled", "reminder.triggered"]
    events_consumed = ["action.started"]

    def __init__(self, *, session_id: str, action_manager: ActionManager) -> None:
        self._session_id = session_id
        self._actions = action_manager
        self._bus: EventBus | None = None
        self._scheduler = ReminderScheduler(self._trigger)

    async def start(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe("action.started", self._on_action_started)
        await bus.publish(
            make_event(
                "system.module_ready",
                source="reminder_module",
                session_id=self._session_id,
                payload={"name": self.name, "component_type": "module", "state": "healthy"},
            )
        )

    async def stop(self) -> None:
        await self._scheduler.stop()

    async def health_check(self) -> HealthState:
        return HealthState.HEALTHY

    async def _on_action_started(self, event: Event) -> None:
        if event.payload.get("action_type") != "remind.schedule" or self._bus is None:
            return
        payload = event.payload.get("payload")
        args = payload if isinstance(payload, dict) else {}
        delay_sec = _delay_sec(args)
        text = str(args.get("text") or "提醒")
        save_path = str(args["save_path"]) if args.get("save_path") else None
        action_id = event.action_id or ""
        self._scheduler.schedule(delay_sec=delay_sec, text=text)
        result = {"delay_sec": delay_sec, "text": text, "scheduled": True}
        if save_path is not None:
            result["save_path"] = save_path
        await self._bus.publish(
            make_event(
                "reminder.scheduled",
                source="reminder_module",
                session_id=self._session_id,
                action_id=action_id,
                turn_id=event.turn_id,
                payload=result,
            )
        )
        await self._actions.complete_action(action_id, result)

    async def _trigger(self, text: str) -> None:
        if self._bus is not None:
            await self._bus.publish(
                make_event(
                    "reminder.triggered",
                    source="reminder_module",
                    session_id=self._session_id,
                    payload={"text": text},
                )
            )
        await self._actions.request_action(
            "speak",
            {"text": text},
            resource="speaker",
            priority=Priority.NORMAL,
        )


def _delay_sec(payload: dict[object, object]) -> float:
    raw = payload.get("delay_sec", 0)
    if isinstance(raw, (int, float, str)):
        return max(float(raw), 0.0)
    return 0.0
