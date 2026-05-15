"""Safety event payloads."""

from __future__ import annotations

from pydantic import BaseModel


class EmergencyStopPayload(BaseModel):
    reason: str = "user_request"
    source: str = "policy"
