"""Runtime safety watchdog independent of EventBus dispatch."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress

from roamerd.events import Priority, make_event
from roamerd.kernel.event_bus import EventBus

SafetyStopCallback = Callable[[], Awaitable[None]]


class SafetyWatchdog:
    def __init__(
        self,
        *,
        session_id: str,
        bus: EventBus,
        stop_motion: SafetyStopCallback,
        timeout_sec: float = 1.0,
        interval_sec: float = 0.1,
    ) -> None:
        self._session_id = session_id
        self._bus = bus
        self._stop_motion = stop_motion
        self._timeout_sec = timeout_sec
        self._interval_sec = interval_sec
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping = False
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping = True
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        while not self._stopping:
            await asyncio.sleep(self._interval_sec)
            elapsed_ms = self._bus.dispatch_stall_elapsed_ms(self._timeout_sec)
            if elapsed_ms is None:
                continue
            self._bus.mark_dispatch_watchdog_triggered()
            payload: dict[str, object] = {"elapsed_ms": elapsed_ms}
            try:
                await self._stop_motion()
            except Exception as exc:
                payload["callback_error"] = str(exc)
            await self._bus.publish(
                make_event(
                    "system.watchdog_triggered",
                    source="safety_watchdog",
                    session_id=self._session_id,
                    payload=payload,
                    priority=Priority.CRITICAL,
                )
            )
