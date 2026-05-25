from __future__ import annotations

from typing import Protocol


class BatchAsrDriver(Protocol):
    async def transcribe(self, pcm: bytes) -> str: ...
