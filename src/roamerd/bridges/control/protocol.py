from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from roamerd.types import JSONDict


class ProtocolError(ValueError):
    pass


class RequestEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "v1"
    request_id: str
    trace_id: str | None = None
    client: str = "unknown"
    source: str = "unknown"
    actor: str | None = None
    authority: str | None = None
    op: str
    timeout_ms: int = 30_000
    args: JSONDict = Field(default_factory=dict)
    wait: Literal["accepted", "result"] = "result"


class ResponseEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "v1"
    request_id: str
    trace_id: str | None = None
    status: Literal["ok", "error"]
    op: str
    action_id: str | None = None
    result: JSONDict = Field(default_factory=dict)
    error: JSONDict | None = None


def decode_request_line(raw: bytes, *, max_bytes: int = 64 * 1024) -> RequestEnvelope:
    if len(raw) > max_bytes:
        raise ProtocolError("message too large")
    try:
        return RequestEnvelope.model_validate_json(raw.strip())
    except Exception as exc:
        raise ProtocolError("malformed request") from exc


def encode_response(response: ResponseEnvelope) -> bytes:
    return response.model_dump_json(exclude_none=True).encode() + b"\n"
