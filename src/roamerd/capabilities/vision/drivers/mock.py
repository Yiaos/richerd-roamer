"""Mock camera driver."""

from __future__ import annotations

from pathlib import Path

from roamerd.kernel.state_manager import HealthState


class MockCameraDriver:
    async def capture(
        self, *, output: str | None = None, width: int | None = None, height: int | None = None
    ) -> dict[str, object]:
        path = output or "/tmp/roamerd-image.jpg"
        Path(path).write_bytes(b"\xff\xd8\xff\xd9")
        return {"ok": True, "path": path, "width": width or 1280, "height": height or 720}

    async def health_check(self) -> HealthState:
        return HealthState.HEALTHY
