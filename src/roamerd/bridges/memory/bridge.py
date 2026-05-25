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

    def __init__(
        self,
        *,
        sink: MemorySink,
        flush_size: int = 10,
        max_consecutive_failures: int = 5,
    ) -> None:
        self._sink = sink
        self._flush_size = flush_size
        self._max_consecutive_failures = max_consecutive_failures
        self._buffer: list[JSONDict] = []
        self._bus: EventBus | None = None
        self._consecutive_flush_failures = 0

    async def start(self, bus: EventBus) -> None:
        self._bus = bus
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
        except Exception as exc:
            self._consecutive_flush_failures += 1
            await self._publish_flush_failed(exc)
            if self._consecutive_flush_failures >= self._max_consecutive_failures:
                keep = self._flush_size * 3
                self._buffer = self._buffer[-keep:]
            return
        self._consecutive_flush_failures = 0
        self._buffer.clear()

    @property
    def buffered_count(self) -> int:
        return len(self._buffer)

    async def _publish_flush_failed(self, exc: Exception) -> None:
        if self._bus is None:
            return
        await self._bus.publish(
            Event(
                event_type="memory.flush_failed",
                source="memory",
                session_id="",
                payload={
                    "reason": str(exc),
                    "buffer_size": len(self._buffer),
                    "failure_count": self._consecutive_flush_failures,
                },
            )
        )
