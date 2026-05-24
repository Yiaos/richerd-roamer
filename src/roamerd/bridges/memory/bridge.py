from __future__ import annotations

from roamerd.events import Event
from roamerd.kernel import EventBus
from roamerd.types import JSONDict


class MemorySink:
    def __init__(self) -> None:
        self.delivered: list[JSONDict] = []

    async def deliver(self, candidates: list[JSONDict]) -> None:
        self.delivered.extend(candidates)


class MemoryBridge:
    name = "memory"

    def __init__(self, *, sink: MemorySink, flush_size: int = 10) -> None:
        self._sink = sink
        self._flush_size = flush_size
        self._buffer: list[JSONDict] = []

    async def start(self, bus: EventBus) -> None:
        bus.subscribe("memory.candidate_raised", self._handle_candidate)

    async def stop(self) -> None:
        await self.flush()

    async def health_check(self) -> str:
        return "healthy"

    async def _handle_candidate(self, event: Event) -> None:
        self._buffer.append(dict(event.payload))
        if len(self._buffer) >= self._flush_size:
            await self.flush()

    async def flush(self) -> None:
        if not self._buffer:
            return
        candidates = list(self._buffer)
        try:
            await self._sink.deliver(candidates)
        except Exception:
            return
        self._buffer.clear()

    @property
    def buffered_count(self) -> int:
        return len(self._buffer)
