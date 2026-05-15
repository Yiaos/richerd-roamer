"""Mock speech drivers."""

from __future__ import annotations

from pathlib import Path

from roamerd.kernel.state_manager import HealthState


class MockTtsDriver:
    async def synthesize(
        self, text: str, output_path: str, *, style: str | None = None
    ) -> dict[str, object]:
        Path(output_path).write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
        return {"ok": True, "path": output_path, "duration_sec": 0.0, "style": style}

    async def health_check(self) -> HealthState:
        return HealthState.HEALTHY


class MockPlaybackDriver:
    def __init__(self) -> None:
        self.stopped = False
        self.played: list[str] = []

    async def play(self, audio_path: str, *, device: str = "default") -> dict[str, object]:
        self.played.append(audio_path)
        return {"ok": True, "duration_sec": 0.0, "device": device}

    async def stop(self) -> None:
        self.stopped = True

    async def health_check(self) -> HealthState:
        return HealthState.HEALTHY
