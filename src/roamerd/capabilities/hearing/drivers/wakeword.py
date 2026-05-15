"""Wakeword driver adapters for HearingModule."""

from __future__ import annotations

import asyncio
import importlib
from typing import Any

from roamerd.config.schema import WakewordConfig
from roamerd.events.hearing import WakePayload
from roamerd.kernel.state_manager import HealthState


class LegacyWakeDriver:
    def __init__(self, *, source: str, legacy_driver: Any, phrase: str | None = None) -> None:
        self._source = source
        self._legacy = legacy_driver
        self._phrase = phrase

    async def start(self) -> None:
        await asyncio.to_thread(self._legacy.start)

    async def stop(self) -> None:
        await asyncio.to_thread(self._legacy.stop)

    async def wait_for_wake(self) -> WakePayload | None:
        hit = await asyncio.to_thread(self._legacy.wait_hit, None)
        if not hit:
            return None
        return WakePayload(source=self._source, phrase=self._phrase)

    async def health_check(self) -> HealthState:
        return HealthState.HEALTHY


def build_wake_driver(config: WakewordConfig) -> LegacyWakeDriver | None:
    if not config.enabled:
        return None
    if config.driver == "su03t_gpio":
        module = importlib.import_module("roamer.plugins.interaction.drivers.wakeword.su03t_gpio")
        legacy = module.Su03tGpioDriver(
            {
                "gpio_chip": config.su03t_gpio.gpio_chip,
                "gpio_line": config.su03t_gpio.gpio_line,
                "edge": config.su03t_gpio.edge,
                "pull": config.su03t_gpio.pull,
                "debounce_ms": config.su03t_gpio.debounce_ms,
                "min_interval_sec": config.min_interval_sec,
            }
        )
        return LegacyWakeDriver(source="su03t_gpio", legacy_driver=legacy, phrase=None)
    if config.driver == "openwakeword":
        module = importlib.import_module("roamer.plugins.interaction.drivers.wakeword.openwakeword")
        legacy = module.OpenWakewordDriver(
            {
                "model": config.model,
                "threshold": config.threshold,
                "min_interval_sec": config.min_interval_sec,
            }
        )
        phrase = config.phrases[0] if config.phrases else None
        return LegacyWakeDriver(source="openwakeword", legacy_driver=legacy, phrase=phrase)
    raise ValueError(f"unsupported wakeword driver: {config.driver}")
