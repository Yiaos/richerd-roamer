"""Legacy leaf adapters for batch listen/STT.

These adapters reuse old I/O leaves without importing the old wake/converse
orchestration spine.
"""

from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
from typing import Any

from roamerd.config.schema import FunAsrConfig, HearingAudioConfig
from roamerd.events.hearing import TranscriptPayload
from roamerd.kernel.state_manager import HealthState


class LegacyBatchSttDriver:
    """Record via the configured audio driver, then transcribe with FunASR."""

    def __init__(self, *, audio: HearingAudioConfig, funasr: FunAsrConfig) -> None:
        audio_module = importlib.import_module("roamer.plugins.interaction.drivers.audio.alsa")
        asr_module = importlib.import_module("roamer.plugins.interaction.drivers.speech.asr.funasr")
        audio_config = {
            "capture_device": audio.alsa.capture_device,
            "sample_rate": audio.alsa.sample_rate,
            "channels": audio.alsa.channels,
        }
        asr_config = funasr.model_dump()
        self._audio_driver: Any = audio_module.AlsaDriver(audio_config)
        self._asr_driver: Any = asr_module.FunASRDriver(asr_config)

    async def transcribe(
        self, audio_path: str | None = None, *, timeout: float = 10.0
    ) -> TranscriptPayload:
        path = audio_path or f"/tmp/roamerd-listen-{id(self)}.wav"
        record_result = await asyncio.to_thread(self._audio_driver.record, path, timeout)
        if not bool(record_result.get("ok", False)):
            raise RuntimeError(str(record_result.get("message", "audio record failed")))
        asr_result = await asyncio.to_thread(self._asr_driver.transcribe, path)
        if not bool(asr_result.get("ok", False)):
            raise RuntimeError(str(asr_result.get("message", "ASR failed")))
        return TranscriptPayload(
            text=str(asr_result.get("text", "")),
            confidence=_confidence(asr_result.get("confidence")),
            audio_path=path,
            duration_sec=_float_or_none(record_result.get("duration_sec")),
        )

    async def health_check(self) -> HealthState:
        return HealthState.HEALTHY


class ExistingAudioBatchSttDriver:
    """Transcribe an existing audio path with FunASR."""

    def __init__(self, config: FunAsrConfig) -> None:
        asr_module = importlib.import_module("roamer.plugins.interaction.drivers.speech.asr.funasr")
        self._asr_driver: Any = asr_module.FunASRDriver(config.model_dump())

    async def transcribe(
        self, audio_path: str | None = None, *, timeout: float = 10.0
    ) -> TranscriptPayload:
        if audio_path is None:
            raise RuntimeError("audio_path is required for existing-audio transcription")
        if not Path(audio_path).exists():
            raise RuntimeError(f"audio file not found: {audio_path}")
        asr_result = await asyncio.to_thread(self._asr_driver.transcribe, audio_path)
        if not bool(asr_result.get("ok", False)):
            raise RuntimeError(str(asr_result.get("message", "ASR failed")))
        return TranscriptPayload(
            text=str(asr_result.get("text", "")),
            confidence=_confidence(asr_result.get("confidence")),
            audio_path=audio_path,
        )

    async def health_check(self) -> HealthState:
        return HealthState.HEALTHY


def _confidence(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else 1.0


def _float_or_none(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None
