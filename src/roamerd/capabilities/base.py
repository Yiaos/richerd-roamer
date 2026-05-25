from __future__ import annotations

from typing import Protocol

from roamerd.kernel.event_bus import EventBus


class CapabilityModule(Protocol):
    name: str
    events_produced: list[str]
    events_consumed: list[str]
    resources: list[str]

    async def start(self, bus: EventBus) -> None: ...

    async def stop(self) -> None: ...

    async def health_check(self) -> str: ...
