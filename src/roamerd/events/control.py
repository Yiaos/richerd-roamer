"""Control bridge command payloads."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from roamerd.events.base import JSONDict


class WaitMode(StrEnum):
    ACCEPTED = "accepted"
    COMPLETED = "completed"


class ControlCommandPayload(BaseModel):
    version: int = 1
    request_id: str | None = None
    trace_id: str | None = None
    client: str = "unknown"
    source: str = "cli"
    actor: str = "unknown"
    authority: str = "owner"
    op: Literal["run", "query", "action.cancel", "action.status"] = "run"
    action: str | None = None
    args: JSONDict = Field(default_factory=dict)
    target: str | None = None
    timeout_ms: int = 30000
    wait: WaitMode = WaitMode.ACCEPTED
    correlation_id: str


class ControlResponsePayload(BaseModel):
    correlation_id: str
    ok: bool
    request_id: str | None = None
    result: JSONDict | None = None
    error_code: str | None = None
    error_message: str | None = None
    action_id: str | None = None
    duration_ms: int | None = None
