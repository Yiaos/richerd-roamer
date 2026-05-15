"""Legacy TTS/playback/bluetooth leaf adapters."""

from __future__ import annotations

import asyncio
import importlib
from typing import Any

from roamerd.config.schema import BluetoothConfig, PlaybackConfig, TtsConfig
from roamerd.kernel.state_manager import HealthState


class LegacyTtsDriver:
    def __init__(self, config: TtsConfig) -> None:
        if config.primary == "piper":
            module = importlib.import_module("roamer.plugins.interaction.drivers.speech.tts.piper")
            self._driver: Any = module.PiperDriver(config.piper.model_dump())
        else:
            module = importlib.import_module("roamer.plugins.interaction.drivers.speech.tts.edge")
            self._driver = module.EdgeDriver(config.edge.model_dump())

    async def synthesize(
        self, text: str, output_path: str, *, style: str | None = None
    ) -> dict[str, object]:
        result = await asyncio.to_thread(self._driver.synthesize, text, output_path, style)
        return result if isinstance(result, dict) else {"ok": False, "error": "invalid TTS result"}

    async def health_check(self) -> HealthState:
        return HealthState.HEALTHY


class LegacyAlsaPlaybackDriver:
    def __init__(self, config: PlaybackConfig) -> None:
        module = importlib.import_module("roamer.plugins.interaction.drivers.audio.alsa")
        self._driver: Any = module.AlsaDriver(
            {
                "playback_device": config.alsa.playback_device,
                "sample_rate": config.alsa.sample_rate,
                "channels": config.alsa.channels,
            }
        )

    async def play(self, audio_path: str, *, device: str = "default") -> dict[str, object]:
        result = await asyncio.to_thread(self._driver.play, audio_path)
        return (
            result
            if isinstance(result, dict)
            else {"ok": False, "error": "invalid playback result"}
        )

    async def stop(self) -> None:
        return None

    async def health_check(self) -> HealthState:
        return HealthState.HEALTHY


class LegacyBluezBluetoothDriver:
    def __init__(self, config: BluetoothConfig) -> None:
        module = importlib.import_module("roamer.plugins.interaction.drivers.bluetooth.bluez")
        self._driver: Any = module.BluezDriver({"speaker_mac": config.speaker_mac})
        self._speaker_mac = config.speaker_mac

    async def ensure_connected(self) -> bool:
        if not self._speaker_mac:
            return False
        result = await asyncio.to_thread(self._driver.connect, self._speaker_mac)
        return bool(result.get("ok", False)) if isinstance(result, dict) else False

    async def disconnect(self) -> None:
        if self._speaker_mac:
            await asyncio.to_thread(self._driver.disconnect, self._speaker_mac)

    async def health_check(self) -> HealthState:
        result = await asyncio.to_thread(self._driver.status)
        return (
            HealthState.HEALTHY
            if isinstance(result, dict) and result.get("ok")
            else HealthState.DEGRADED
        )
