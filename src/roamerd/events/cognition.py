from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from roamerd.types import JSONDict


class CognitionRequestNeeded(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["cognition.request_needed"]] = "cognition.request_needed"

    text: str
    context_hint: JSONDict = {}


class CognitionResponseReceived(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["cognition.response_received"]] = "cognition.response_received"

    kind: str
    payload: JSONDict
    confidence: float | None = None


class CognitionUnavailable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["cognition.unavailable"]] = "cognition.unavailable"

    reason: str
    request_id: str | None = None
