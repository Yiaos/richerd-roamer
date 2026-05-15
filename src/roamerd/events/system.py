"""System event payloads."""

from __future__ import annotations

from pydantic import BaseModel


class HealthChangedPayload(BaseModel):
    name: str
    component_type: str = "module"
    state: str
    reason: str | None = None


class ModuleReadyPayload(BaseModel):
    name: str
    component_type: str = "module"
