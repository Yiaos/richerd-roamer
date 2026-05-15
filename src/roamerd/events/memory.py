"""Memory bridge payloads."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from roamerd.events.base import JSONDict, JSONValue


class MemoryCandidatePayload(BaseModel):
    candidate_type: str
    summary: str
    details: JSONDict = Field(default_factory=dict)
    importance: float = 0.5
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    turn_id: str | None = None


class PolicyRule(BaseModel):
    rule_type: str
    value: JSONValue
    source: str = "memory"
    expires_at: datetime | None = None


class PolicyUpdatePayload(BaseModel):
    updates: list[PolicyRule] = Field(default_factory=list)
