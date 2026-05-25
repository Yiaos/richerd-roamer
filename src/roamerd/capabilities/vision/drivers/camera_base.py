from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class CaptureResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: Path
    timestamp: datetime
    width: int | None = None
    height: int | None = None


class CameraDriver(Protocol):
    async def capture(
        self,
        output_path: Path,
        *,
        width: int | None = None,
        height: int | None = None,
    ) -> CaptureResult: ...
