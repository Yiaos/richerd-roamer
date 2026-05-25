from __future__ import annotations

from pathlib import Path

from roamerd.capabilities.speech.drivers.tts_base import SynthResult


class MockTtsDriver:
    async def synthesize(self, text: str, output_path: Path) -> SynthResult:
        return SynthResult(path=output_path, duration_ms=max(len(text) * 10, 1))


class MockPlaybackDriver:
    async def play(self, path: Path) -> None:
        return None


class MockBluetoothDriver:
    async def status(self) -> str:
        return "connected"

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None
