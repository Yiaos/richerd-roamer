from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from roamerd.capabilities.vision.drivers.camera_base import CaptureResult


class MockCameraDriver:
    async def capture(
        self,
        output_path: Path,
        *,
        width: int | None = None,
        height: int | None = None,
    ) -> CaptureResult:
        return CaptureResult(
            path=output_path,
            timestamp=datetime.now(UTC),
            width=width,
            height=height,
        )
