"""fswebcam driver adapter."""

from __future__ import annotations

import asyncio
import importlib
from typing import Any

from roamerd.config.schema import FswebcamConfig
from roamerd.kernel.state_manager import HealthState


class FswebcamCameraDriver:
    def __init__(self, config: FswebcamConfig) -> None:
        module = importlib.import_module("roamer.plugins.perception.drivers.camera_fswebcam")
        self._config = config
        self._driver: Any = module.FswebcamDriver(config.model_dump())

    async def capture(
        self, *, output: str | None = None, width: int | None = None, height: int | None = None
    ) -> dict[str, object]:
        path = output or "/tmp/roamerd-watch.jpg"
        result = await asyncio.to_thread(
            self._driver.snap,
            path,
            width or self._config.width,
            height or self._config.height,
        )
        return (
            result if isinstance(result, dict) else {"ok": False, "error": "invalid camera result"}
        )

    async def health_check(self) -> HealthState:
        return HealthState.HEALTHY
