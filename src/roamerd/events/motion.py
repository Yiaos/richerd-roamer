from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict


class MotionStopRequested(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["motion.stop_requested"]] = "motion.stop_requested"

    reason: str


class MotionStarted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["motion.started"]] = "motion.started"

    action_id: str
    target: dict[str, float] | None = None


class MotionCompleted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["motion.completed"]] = "motion.completed"

    action_id: str
    status: str


class MotionFailed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["motion.failed"]] = "motion.failed"

    action_id: str
    error_code: str
    message: str


class MotionPositionUpdated(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["motion.position_updated"]] = "motion.position_updated"

    x: float
    y: float
    angle: float | None = None


class MotionStatusUpdated(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["motion.status_updated"]] = "motion.status_updated"

    status: str
    battery_percent: float | None = None
