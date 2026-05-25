from __future__ import annotations

from typing import Protocol


class AudioCaptureDriver(Protocol):
    async def record(self) -> bytes: ...
