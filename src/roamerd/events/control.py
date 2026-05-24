from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from roamerd.types import JSONDict


class ControlCommandReceived(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["control.command_received"]] = "control.command_received"

    request_id: str
    op: str
    args: JSONDict


class ControlResponseReady(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["control.response_ready"]] = "control.response_ready"

    request_id: str
    status: str


class ControlResponseSent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["control.response_sent"]] = "control.response_sent"

    request_id: str
    bytes_sent: int
