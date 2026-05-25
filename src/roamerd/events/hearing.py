from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict


class WakeTriggered(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["hearing.wake_triggered"]] = "hearing.wake_triggered"

    wakeword: str
    confidence: float
    follow_up: bool = False


class RecordingStarted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["hearing.recording_started"]] = "hearing.recording_started"

    device: str | None = None
    sample_rate: int
    channels: int


class SpeechEndpointDetected(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["hearing.speech_endpoint_detected"]] = (
        "hearing.speech_endpoint_detected"
    )

    audio_path: str | None = None
    duration_ms: int
    speech_ms: int


class TranscriptReady(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["hearing.transcript_ready"]] = "hearing.transcript_ready"

    text: str
    confidence: float | None = None
    follow_up_eligible: bool = False
    fallback_eligible: bool = True


class ListenFailed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["hearing.listen_failed"]] = "hearing.listen_failed"

    error_code: str
    message: str


class AudioLevelChanged(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["hearing.audio_level_changed"]] = "hearing.audio_level_changed"

    rms: float
    peak: float
