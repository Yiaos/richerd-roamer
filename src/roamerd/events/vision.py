from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from roamerd.types import JSONDict


class ImageCaptured(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["vision.image_captured"]] = "vision.image_captured"

    path: str
    width: int | None = None
    height: int | None = None


class SceneObserved(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["vision.scene_observed"]] = "vision.scene_observed"

    description: str | None = None
    objects: list[JSONDict] = Field(default_factory=list)


class PersonDetected(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["vision.person_detected"]] = "vision.person_detected"

    person_id: str | None = None
    name: str | None = None
    confidence: float | None = None
    position_hint: str | None = None
    source: str | None = None


class CaptureFailed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["vision.capture_failed"]] = "vision.capture_failed"

    error_code: str
    message: str
