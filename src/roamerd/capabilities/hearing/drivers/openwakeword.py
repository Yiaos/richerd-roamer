from __future__ import annotations

from collections.abc import Awaitable, Callable

from roamerd.capabilities.hearing.drivers.wakeword_base import WakeEvent

Detector = Callable[[], Awaitable[tuple[str, float]]]


class OpenWakewordDriver:
    def __init__(self, *, detector: Detector) -> None:
        self._detector = detector

    async def wait_for_wake(self) -> WakeEvent:
        wakeword, confidence = await self._detector()
        return WakeEvent(wakeword=wakeword, confidence=confidence)
