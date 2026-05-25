from __future__ import annotations

from pathlib import Path
from typing import Protocol

from roamerd.capabilities.speech.drivers.bluetooth_base import BluetoothDriver


class PlaybackDriver(Protocol):
    async def play(self, path: Path) -> None: ...


class BluetoothPlaybackDriver:
    def __init__(self, playback: PlaybackDriver, bluetooth: BluetoothDriver) -> None:
        self._playback = playback
        self._bluetooth = bluetooth

    async def play(self, path: Path) -> None:
        if await self._bluetooth.status() != "connected":
            await self._bluetooth.connect()
        await self._playback.play(path)
