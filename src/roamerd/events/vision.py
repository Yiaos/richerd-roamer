from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict


class ImageCaptured(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["vision.image_captured"]] = "vision.image_captured"

    path: str
    width: int | None = None
    height: int | None = None


class SceneObserved(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["vision.scene_observed"]] = "vision.scene_observed"

    summary: str
    confidence: float | None = None


class PersonDetected(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["vision.person_detected"]] = "vision.person_detected"

    person_id: str | None = None
    label: str | None = None
    confidence: float | None = None


class CaptureFailed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["vision.capture_failed"]] = "vision.capture_failed"

    error_code: str
    message: str
