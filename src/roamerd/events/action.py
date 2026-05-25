from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from roamerd.types import JSONDict


class ActionStarted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["action.started"]] = "action.started"

    action_id: str
    action_type: str
    resource: str


class ActionCompleted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["action.completed"]] = "action.completed"

    action_id: str
    result: JSONDict


class ActionFailed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["action.failed"]] = "action.failed"

    action_id: str
    error: JSONDict


class ActionCancelled(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["action.cancelled"]] = "action.cancelled"

    action_id: str
    reason: str


class ActionPreempted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["action.preempted"]] = "action.preempted"

    action_id: str
    reason: str


class ActionCancelRequested(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["action.cancel_requested"]] = "action.cancel_requested"

    action_id: str
    reason: str


class ActionPreemptRequested(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["action.preempt_requested"]] = "action.preempt_requested"

    action_id: str
    reason: str


class ActionDetached(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["action.detached"]] = "action.detached"

    action_id: str
    reason: str
