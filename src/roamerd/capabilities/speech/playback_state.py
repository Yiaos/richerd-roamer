from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class PlaybackState:
    active: bool = False
    generation: int = 0
    stale_after_sec: float = 120.0
    started_at: float | None = None

    def started(self, *, now: float | None = None) -> int:
        self.active = True
        self.started_at = now if now is not None else time.monotonic()
        self.generation += 1
        return self.generation

    def finished(self) -> int:
        self.active = False
        self.started_at = None
        self.generation += 1
        return self.generation

    def stale(self, *, now: float | None = None) -> bool:
        if not self.active or self.started_at is None:
            return False
        current = now if now is not None else time.monotonic()
        return current - self.started_at > self.stale_after_sec
