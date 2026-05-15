"""Bridge protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.state_manager import HealthState


@runtime_checkable
class Bridge(Protocol):
    name: str

    async def start(self, bus: EventBus) -> None: ...

    async def stop(self) -> None: ...

    async def health_check(self) -> HealthState: ...
