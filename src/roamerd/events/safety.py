from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict


class EmergencyStopRequested(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["safety.emergency_stop_requested"]] = (
        "safety.emergency_stop_requested"
    )

    reason: str


class SafetyTriggered(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["safety.triggered"]] = "safety.triggered"

    reason: str
    severity: str


class SafetyStopApplied(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["safety.stop_applied"]] = "safety.stop_applied"

    reason: str
    stopped_resources: list[str]
