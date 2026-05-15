"""Memory bridge with local buffer fallback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from roamerd.events.base import Event, make_event
from roamerd.events.memory import MemoryCandidatePayload
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.state_manager import HealthState


@runtime_checkable
class MemoryAdapter(Protocol):
    async def submit_candidate(self, candidate: MemoryCandidatePayload) -> bool: ...

    async def health_check(self) -> HealthState: ...


class MemoryBridge:
    name = "memory"

    def __init__(
        self, *, session_id: str, buffer_path: str, adapter: MemoryAdapter | None = None
    ) -> None:
        self._session_id = session_id
        self._buffer_path = Path(buffer_path)
        self._adapter = adapter

    async def start(self, bus: EventBus) -> None:
        bus.subscribe("memory.candidate_raised", self._on_candidate)
        await bus.publish(
            make_event(
                "system.module_ready",
                source="memory_bridge",
                session_id=self._session_id,
                payload={
                    "name": self.name,
                    "component_type": "bridge",
                    "state": "degraded" if self._adapter is None else "healthy",
                },
            )
        )

    async def stop(self) -> None:
        return None

    async def health_check(self) -> HealthState:
        return HealthState.DEGRADED if self._adapter is None else await self._adapter.health_check()

    async def _on_candidate(self, event: Event) -> None:
        candidate = MemoryCandidatePayload.model_validate(event.payload)
        if self._adapter is not None and await self._adapter.submit_candidate(candidate):
            return
        self._buffer_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._buffer_path, "a") as handle:
            handle.write(json.dumps(candidate.model_dump(mode="json"), ensure_ascii=False) + "\n")
