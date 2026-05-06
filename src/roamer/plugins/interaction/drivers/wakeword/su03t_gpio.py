"""SU-03T GPIO wake trigger driver."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from roamer.plugins.interaction.drivers.registry import register_driver
from roamer.plugins.interaction.drivers.wakeword.base import WakewordDriver


class Su03tGpioDriver(WakewordDriver):
    """Wait for SU-03T digital wake output on a Raspberry Pi GPIO line."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._request: Any | None = None
        self._last_hit: float | None = None
        self._clock: Callable[[], float] = config.get("clock") or time.monotonic

    def start(self) -> None:
        request_factory = self.config.get("request_factory") or _create_gpiod_request
        self._request = request_factory(self.config)

    def stop(self) -> None:
        if self._request is not None:
            release = getattr(self._request, "release", None)
            if callable(release):
                release()
        self._request = None

    def wait_hit(self, timeout: float) -> bool:
        if self._request is None:
            return False

        wait_edge_events = getattr(self._request, "wait_edge_events")
        read_edge_events = getattr(self._request, "read_edge_events")
        if not wait_edge_events(timeout):
            return False
        events = list(read_edge_events())
        if not events:
            return False

        now = self._clock()
        min_interval = float(self.config.get("min_interval_sec", 1.5))
        if self._last_hit is not None and now - self._last_hit < min_interval:
            return False

        self._last_hit = now
        return True


def _create_gpiod_request(config: dict[str, Any]) -> Any:
    try:
        import gpiod
        from gpiod.line import Bias, Direction, Edge
    except ImportError as exc:
        raise RuntimeError("Python gpiod package is required for su03t_gpio") from exc

    chip_path = f"/dev/{config.get('gpio_chip', 'gpiochip0')}"
    line = int(config.get("gpio_line", 17))
    edge_name = str(config.get("edge", "rising")).lower()
    pull_name = str(config.get("pull", "down")).lower()

    edge = Edge.RISING if edge_name == "rising" else Edge.FALLING
    bias = Bias.PULL_DOWN if pull_name == "down" else Bias.PULL_UP
    debounce_period = timedelta(milliseconds=float(config.get("debounce_ms", 300)))

    settings = gpiod.LineSettings(
        direction=Direction.INPUT,
        edge_detection=edge,
        bias=bias,
        debounce_period=debounce_period,
    )
    return gpiod.request_lines(
        chip_path,
        consumer="roamer-su03t-wake",
        config={line: settings},
    )


register_driver("wakeword", "su03t_gpio", Su03tGpioDriver)
