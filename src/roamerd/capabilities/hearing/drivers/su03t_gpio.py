from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from roamerd.capabilities.hearing.drivers.wakeword_base import WakeEvent

WaitEdge = Callable[[], Awaitable[None]]
Clock = Callable[[], float]


class Su03tGpioWakewordDriver:
    def __init__(
        self,
        *,
        wait_edge: WaitEdge | None = None,
        clock: Clock = time.monotonic,
        min_interval_sec: float = 1.5,
        wakeword: str = "su03t",
    ) -> None:
        self._wait_edge = wait_edge or _missing_wait_edge
        self._clock = clock
        self._min_interval_sec = min_interval_sec
        self._wakeword = wakeword
        self._last_wake_at: float | None = None

    async def wait_for_wake(self) -> WakeEvent:
        while True:
            await self._wait_edge()
            now = self._clock()
            if self._last_wake_at is not None and now - self._last_wake_at < self._min_interval_sec:
                continue
            self._last_wake_at = now
            return WakeEvent(wakeword=self._wakeword, confidence=1.0)


async def _missing_wait_edge() -> None:
    raise RuntimeError("gpiod wait_edge is not configured")
