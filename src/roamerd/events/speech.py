"""Speech event payload models."""

from __future__ import annotations

from pydantic import BaseModel

from roamerd.events.base import Priority


class SpeakRequestPayload(BaseModel):
    text: str
    style: str | None = None
    priority: Priority = Priority.NORMAL
    save_path: str | None = None
    play: bool = True


class SynthesisPayload(BaseModel):
    action_id: str
    text_length: int
    driver: str


class PlaybackPayload(BaseModel):
    action_id: str
    audio_path: str
    duration_sec: float | None = None
    device: str = "default"


class StopPayload(BaseModel):
    reason: str = "user_request"
