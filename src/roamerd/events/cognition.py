from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from roamerd.types import JSONDict


class CognitionRequestNeeded(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["cognition.request_needed"]] = "cognition.request_needed"

    text: str
    reason: str | None = None
    context_hint: JSONDict = Field(default_factory=dict)


class CognitionResponseReceived(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["cognition.response_received"]] = "cognition.response_received"

    response_type: str | None = None
    text: str | None = None
    action_request: JSONDict | None = None
    payload: JSONDict | None = None
    confidence: float | None = None
    latency_ms: float | None = None
    correlation_id: str | None = None


class CognitionUnavailable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["cognition.unavailable"]] = "cognition.unavailable"

    reason: str
    request_id: str | None = None
    correlation_id: str | None = None
