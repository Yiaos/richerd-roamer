"""Motion event payload models."""

from __future__ import annotations

from pydantic import BaseModel

from roamerd.events.base import Priority


class Position(BaseModel):
    x: float
    y: float
    angle: float | None = None
    frame: str = "valetudo_pixel"


class MotionTarget(BaseModel):
    x: float
    y: float
    angle: float | None = None
    frame: str = "valetudo_pixel"
    name: str | None = None


class MoveRequestPayload(BaseModel):
    target: MotionTarget
    priority: Priority = Priority.HIGH
    wait: bool = True


class HomeRequestPayload(BaseModel):
    reason: str = "user_request"
    wait: bool = True


class MotionStartedPayload(BaseModel):
    action_id: str
    target: MotionTarget | None = None


class MotionCompletedPayload(BaseModel):
    action_id: str
    final_position: Position | None = None
    duration_sec: float = 0.0


class MotionFailedPayload(BaseModel):
    action_id: str
    error_code: str
    error_message: str


class PositionPayload(BaseModel):
    position: Position
    source: str = "ros2"


class MotionStatusPayload(BaseModel):
    battery_percent: int | None = None
    docked: bool | None = None
    state: str | None = None
