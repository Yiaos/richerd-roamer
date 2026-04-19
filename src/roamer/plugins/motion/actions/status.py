"""motion.status action."""

from __future__ import annotations

from typing import Any

from roamer.plugins.motion.drivers.valetudo import ValetudoMotionDriver


class MotionStatusAction:
    """Return current motion status from Valetudo."""

    def __init__(self, config: dict[str, Any]):
        self._driver = ValetudoMotionDriver(config.get("valetudo", {}))

    def run(self) -> dict[str, Any]:
        return self._driver.get_status()
