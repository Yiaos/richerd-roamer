from __future__ import annotations

from typing import Protocol


class RealtimeSttDriver(Protocol):
    async def transcribe(self, pcm: bytes) -> str: ...
