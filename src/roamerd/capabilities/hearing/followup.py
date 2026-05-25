from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FollowupCoordinator:
    generation: int = 0
    open: bool = False

    def open_window(self) -> int:
        self.generation += 1
        self.open = True
        return self.generation

    def close_if_current(self, generation: int) -> bool:
        if generation != self.generation:
            return False
        self.open = False
        return True
