"""motion.locate action."""

from __future__ import annotations

from typing import Any

from roamer.plugins.motion.drivers.valetudo import ValetudoMotionDriver


class MotionLocateAction:
    """Trigger locate action via Valetudo."""

    def __init__(self, config: dict[str, Any]):
        self._driver = ValetudoMotionDriver(config.get("valetudo", {}))

    def run(self) -> dict[str, Any]:
        return self._driver.locate()
