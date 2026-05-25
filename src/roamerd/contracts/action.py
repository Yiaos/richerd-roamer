from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from roamerd.events import Priority
from roamerd.types import JSONDict


class ActionContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActionStatus(StrEnum):
    PENDING = "pending"
    WAITING_RESOURCE = "waiting_resource"
    RUNNING = "running"
    RUNNING_DETACHED = "running_detached"
    PREEMPTING = "preempting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PREEMPTED = "preempted"


class ActionRequest(ActionContractModel):
    action_type: str
    payload: JSONDict = Field(default_factory=dict)
    resource: str = "none"
    priority: Priority = Priority.NORMAL
    source: str
    turn_id: str | None = None


class PreemptionScope(ActionContractModel):
    target_resources: list[str]
    reason: str
    source_event: str
