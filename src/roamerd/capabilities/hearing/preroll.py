from __future__ import annotations

from pathlib import Path


class PreRollAudioSource:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.played = False

    async def play(self) -> None:
        self.played = True
