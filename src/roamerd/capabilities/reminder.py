from __future__ import annotations

import asyncio

from roamerd.events import Event
from roamerd.kernel import ActionManager, EventBus


class ReminderModule:
    name = "reminder"
    events_produced: list[str] = []
    events_consumed = ["action.started", "action.cancel_requested"]
    resources = ["none"]

    def __init__(
        self,
        *,
        action_manager: ActionManager,
        session_id: str = "session-1",
    ) -> None:
        self._actions = action_manager
        self._session_id = session_id
        self._bus: EventBus | None = None
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def start(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe("action.started", self._handle_action_started)
        bus.subscribe("action.cancel_requested", self._handle_cancel_requested)

    async def stop(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    async def health_check(self) -> str:
        return "healthy"

    async def _handle_action_started(self, event: Event) -> None:
        if event.payload.get("action_type") != "remind.schedule":
            return
        action_id = event.action_id or str(event.payload.get("action_id", ""))
        action = self._actions.get_action(action_id)
        if action is None:
            return
        delay_sec = _float_value(action.payload.get("delay_sec"))
        text = _text_value(action.payload.get("text"))
        await self._actions.request_action(
            "speech.speak",
            {"text": f"好的，{int(delay_sec)}秒后提醒你{text}"},
            resource="speaker",
            source_module="reminder",
            turn_id=event.turn_id,
        )
        self._tasks[action_id] = asyncio.create_task(
            self._fire_later(action_id, delay_sec, text, event.turn_id)
        )
        await self._actions.complete_action(
            action_id,
            {"scheduled": True, "delay_sec": delay_sec},
        )

    async def _handle_cancel_requested(self, event: Event) -> None:
        action_id = str(event.payload.get("action_id", ""))
        task = self._tasks.pop(action_id, None)
        if task is None:
            return
        task.cancel()
        await self._actions.mark_cancelled(action_id, "cancelled")

    async def _fire_later(
        self,
        action_id: str,
        delay_sec: float,
        text: str,
        turn_id: str | None,
    ) -> None:
        try:
            await asyncio.sleep(delay_sec)
            await self._actions.request_action(
                "speech.speak",
                {"text": f"提醒：{text}"},
                resource="speaker",
                source_module="reminder",
                turn_id=turn_id,
            )
        finally:
            self._tasks.pop(action_id, None)


def _float_value(value: object) -> float:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        return float(value)
    return 0.0


def _text_value(value: object) -> str:
    return value if isinstance(value, str) and value else "提醒"
