from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict


class WakeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wakeword: str
    confidence: float
    follow_up: bool = False


class WakewordDriver(Protocol):
    async def wait_for_wake(self) -> WakeEvent: ...
