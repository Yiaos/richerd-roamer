"""Canonical typed event envelope for roamerd."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import IntEnum, StrEnum
from typing import Any, TypeAlias
from uuid import uuid4

from pydantic import BaseModel, Field

JSONValue: TypeAlias = Any
JSONDict: TypeAlias = dict[str, Any]


class Priority(IntEnum):
    """Event priority. Higher values dispatch first."""

    LOW = 10
    NORMAL = 20
    HIGH = 30
    CRITICAL = 40

    @classmethod
    def coerce(cls, value: "Priority | str") -> "Priority":
        if isinstance(value, Priority):
            return value
        return {
            "low": cls.LOW,
            "normal": cls.NORMAL,
            "high": cls.HIGH,
            "critical": cls.CRITICAL,
        }[value]

    @property
    def wire_value(self) -> str:
        return {
            Priority.LOW: "low",
            Priority.NORMAL: "normal",
            Priority.HIGH: "high",
            Priority.CRITICAL: "critical",
        }[self]


class EventNamespace(StrEnum):
    HEARING = "hearing"
    SPEECH = "speech"
    VISION = "vision"
    MOTION = "motion"
    SAFETY = "safety"
    COGNITION = "cognition"
    MEMORY = "memory"
    CONTROL = "control"
    POLICY = "policy"
    SYSTEM = "system"
    ACTION = "action"


class Event(BaseModel):
    """Generic event envelope. Payload schemas live in event-specific modules."""

    event_id: str = Field(default_factory=lambda: uuid4().hex[:16])
    event_type: str
    source: str
    priority: Priority = Priority.NORMAL
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    session_id: str
    turn_id: str | None = None
    action_id: str | None = None
    correlation_id: str | None = None
    payload: JSONDict = Field(default_factory=dict)

    def payload_value(self, key: str, default: JSONValue = None) -> JSONValue:
        return self.payload.get(key, default)


def make_event(
    event_type: str,
    *,
    source: str,
    session_id: str,
    payload: JSONDict | None = None,
    priority: Priority = Priority.NORMAL,
    turn_id: str | None = None,
    action_id: str | None = None,
    correlation_id: str | None = None,
) -> Event:
    return Event(
        event_type=event_type,
        source=source,
        session_id=session_id,
        priority=priority,
        payload=payload or {},
        turn_id=turn_id,
        action_id=action_id,
        correlation_id=correlation_id,
    )
