"""Vision event payload models."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class CaptureRequestPayload(BaseModel):
    describe: bool = False
    detect_faces: bool = False
    output: str | None = None
    width: int | None = None
    height: int | None = None


class ImagePayload(BaseModel):
    action_id: str
    path: str
    width: int
    height: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ScenePayload(BaseModel):
    description: str | None = None
    objects: list[str] = Field(default_factory=list)
    image_path: str
    model: str = "local"


class PersonPayload(BaseModel):
    name: str | None = None
    embedding_id: str | None = None
    confidence: float
    bbox: tuple[int, int, int, int] | None = None
