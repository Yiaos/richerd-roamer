"""Mock hearing drivers."""

from __future__ import annotations

from collections import deque

from roamerd.events.hearing import TranscriptPayload
from roamerd.kernel.state_manager import HealthState


class MockSttDriver:
    def __init__(self, transcripts: list[str] | None = None) -> None:
        self._transcripts: deque[str] = deque(transcripts or ["mock transcript"])

    def push(self, text: str) -> None:
        self._transcripts.append(text)

    async def transcribe(
        self, audio_path: str | None = None, *, timeout: float = 10.0
    ) -> TranscriptPayload:
        text = self._transcripts.popleft() if self._transcripts else ""
        return TranscriptPayload(text=text, audio_path=audio_path, duration_sec=0.0)

    async def health_check(self) -> HealthState:
        return HealthState.HEALTHY
