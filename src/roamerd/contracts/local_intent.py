from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from roamerd.events import Priority

ALLOWED_INTENT_ACTIONS = {
    "emergency_stop",
    "hearing.listen",
    "motion.home",
    "motion.goto",
    "motion.position",
    "speech.speak",
    "sense",
    "time.now",
    "watch",
    "remind.schedule",
}


class LocalIntentContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IntentConfig(LocalIntentContractModel):
    name: str
    action: str
    patterns: list[str]
    priority: Priority = Priority.NORMAL


class LocalIntentMatch(LocalIntentContractModel):
    matched: bool
    intent_name: str | None = None
    action_type: str | None = None
    slots: dict[str, str] = Field(default_factory=dict)
    priority: Priority = Priority.NORMAL
    reason: str = ""
