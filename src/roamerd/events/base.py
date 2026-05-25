from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from roamerd.types import JSONDict

_EVENT_TYPE_RE = re.compile(r"^[a-z]+(?:_[a-z0-9]+)*\.[a-z0-9]+(?:_[a-z0-9]+)*$")


class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"

    @property
    def sort_rank(self) -> int:
        return {
            Priority.CRITICAL: 0,
            Priority.HIGH: 1,
            Priority.NORMAL: 2,
            Priority.LOW: 3,
        }[self]


class TypedPayload(Protocol):
    EVENT_TYPE: str

    def model_dump(self) -> dict[str, object]: ...


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: uuid4().hex[:16])
    event_type: str
    source: str
    priority: Priority = Priority.NORMAL
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    session_id: str
    turn_id: str | None = None
    action_id: str | None = None
    correlation_id: str | None = None
    payload: JSONDict = Field(default_factory=dict)
    privacy_level: str = "normal"
    retention_hint: str = "default"

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        if not _EVENT_TYPE_RE.fullmatch(value):
            raise ValueError("event_type must be dotted lowercase")
        return value

    def __lt__(self, other: Event) -> bool:
        if self.priority.sort_rank == other.priority.sort_rank:
            return self.occurred_at < other.occurred_at
        return self.priority.sort_rank < other.priority.sort_rank

    @classmethod
    def from_payload(
        cls,
        payload: TypedPayload,
        *,
        source: str,
        session_id: str,
        priority: Priority = Priority.NORMAL,
        turn_id: str | None = None,
        action_id: str | None = None,
        correlation_id: str | None = None,
        privacy_level: str = "normal",
        retention_hint: str = "default",
    ) -> Event:
        return cls(
            event_type=payload.EVENT_TYPE,
            source=source,
            priority=priority,
            session_id=session_id,
            turn_id=turn_id,
            action_id=action_id,
            correlation_id=correlation_id,
            payload=cast(JSONDict, payload.model_dump()),
            privacy_level=privacy_level,
            retention_hint=retention_hint,
        )
