"""Hearing event payload models."""

from __future__ import annotations

from pydantic import BaseModel


class WakePayload(BaseModel):
    source: str
    phrase: str | None = None
    follow_up: bool = False
    command_text: str | None = None


class RecordConfig(BaseModel):
    max_duration_sec: float = 10.0
    silence_timeout_sec: float = 1.5
    min_duration_sec: float = 0.3
    sample_rate: int = 16000
    channels: int = 1
    save_audio: bool = False


class RecordingPayload(BaseModel):
    action_id: str
    config: RecordConfig


class EndpointPayload(BaseModel):
    action_id: str
    duration_sec: float
    audio_path: str | None = None


class TranscriptPayload(BaseModel):
    text: str
    confidence: float = 1.0
    language: str = "zh"
    audio_path: str | None = None
    duration_sec: float | None = None


class ErrorPayload(BaseModel):
    error_code: str
    error_message: str
    recoverable: bool = True
