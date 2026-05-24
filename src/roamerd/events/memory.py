from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from roamerd.types import JSONDict


class MemoryCandidateRaised(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["memory.candidate_raised"]] = "memory.candidate_raised"

    kind: str
    content: JSONDict


class PolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["memory.policy_update"]] = "memory.policy_update"

    policy_id: str
    enabled: bool
    payload: JSONDict = {}
