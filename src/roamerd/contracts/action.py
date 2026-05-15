"""Action lifecycle contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field

from roamerd.events.base import JSONDict, Priority


class ActionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PREEMPTED = "preempted"


class Action(BaseModel):
    action_id: str = Field(default_factory=lambda: f"act_{uuid4().hex[:12]}")
    action_type: str
    resource: str
    priority: Priority
    status: ActionStatus = ActionStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    turn_id: str | None = None
    payload: JSONDict = Field(default_factory=dict)
    result: JSONDict | None = None
    error: JSONDict | None = None


class PreemptionScope(BaseModel):
    target_resources: list[str]
    reason: str
    source_event: str


class ActionRequest(BaseModel):
    action_type: str
    payload: JSONDict = Field(default_factory=dict)
    resource: str = "none"
    priority: Priority = Priority.NORMAL
    source: str
    turn_id: str | None = None
