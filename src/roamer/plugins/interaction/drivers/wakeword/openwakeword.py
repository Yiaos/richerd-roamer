"""Placeholder openwakeword driver implementation."""

from __future__ import annotations

import time
from typing import Any

from roamer.plugins.interaction.drivers.registry import register_driver
from roamer.plugins.interaction.drivers.wakeword.base import WakewordDriver


class OpenWakewordDriver(WakewordDriver):
    """Minimal placeholder wakeword driver.

    v1 behavior: return no hit by default; supports test override through config.mock_hit.
    """

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._running = False

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def wait_hit(self, timeout: float) -> bool:
        if not self._running:
            return False
        if bool(self.config.get("mock_hit", False)):
            return True
        sleep_for = max(0.0, min(float(timeout), 0.1))
        time.sleep(sleep_for)
        return False


register_driver("wakeword", "openwakeword", OpenWakewordDriver)
