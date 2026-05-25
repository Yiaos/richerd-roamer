from __future__ import annotations

from collections.abc import Callable


class SileroVadDriver:
    def __init__(self, *, model: Callable[[bytes], float], threshold: float = 0.1) -> None:
        self._model = model
        self._threshold = threshold

    async def is_speech(self, pcm: bytes) -> bool:
        return self.probability(pcm) >= self._threshold

    def probability(self, pcm: bytes) -> float:
        return float(self._model(pcm))
