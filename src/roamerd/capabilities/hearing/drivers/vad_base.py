from __future__ import annotations

from typing import Protocol


class VadDriver(Protocol):
    async def is_speech(self, pcm: bytes) -> bool: ...
