from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class SynthResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: Path
    duration_ms: int | None = None


class TtsDriver(Protocol):
    async def synthesize(self, text: str, output_path: Path) -> SynthResult: ...
