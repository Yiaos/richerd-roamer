"""Cognition bridge payload models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from roamerd.events.base import JSONDict


class CognitionResponseType(StrEnum):
    SPEAK = "speak"
    ACTION = "action"
    SPEAK_AND_ACTION = "speak_and_action"
    DECLINE = "decline"
    ERROR = "error"


class ActionIntent(BaseModel):
    action_type: str
    payload: JSONDict = Field(default_factory=dict)
    resource: str = "none"


class CognitionRequestPayload(BaseModel):
    text: str
    turn_id: str
    correlation_id: str


class CognitionResponsePayload(BaseModel):
    correlation_id: str
    response_type: CognitionResponseType
    text: str | None = None
    action_request: ActionIntent | None = None
    latency_ms: int | None = None


class CognitionUnavailablePayload(BaseModel):
    reason: str
    last_available_at: datetime | None = None
