from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict


class SynthesisStarted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["speech.synthesis_started"]] = "speech.synthesis_started"

    text_len: int
    driver: str


class PlaybackStarted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["speech.playback_started"]] = "speech.playback_started"

    path: str
    duration_ms: int | None = None


class PlaybackCompleted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["speech.playback_completed"]] = "speech.playback_completed"

    path: str
    elapsed_ms: int | None = None


class PlaybackFailed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["speech.playback_failed"]] = "speech.playback_failed"

    error_code: str
    message: str


class SpeechStopRequested(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["speech.stop_requested"]] = "speech.stop_requested"

    reason: str
