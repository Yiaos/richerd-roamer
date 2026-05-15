"""Local intent contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from roamerd.events.base import JSONDict


class LocalIntentRule(BaseModel):
    name: str
    action: str
    patterns: list[str]
    priority: str = "normal"


class LocalIntentMatch(BaseModel):
    matched: bool
    intent_name: str | None = None
    action_type: str | None = None
    slots: JSONDict = Field(default_factory=dict)
    reason: str = ""


class PolicyDecision(BaseModel):
    decision_type: Literal[
        "allow", "reject", "preempt", "route_to_cognition", "handle_local", "notify"
    ]
    admitted: bool
    reason: str
    action_id: str | None = None
    preempted: list[str] = Field(default_factory=list)
