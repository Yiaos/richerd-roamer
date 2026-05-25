from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from roamerd.contracts.errors import (
    SCHEMA_VERSION,
    ErrorCode,
    canonical_error_code,
)
from roamerd.types import JSONDict


class ActionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    schema_version: str = SCHEMA_VERSION
    data: JSONDict | None = None
    error: str | None = None
    error_code: ErrorCode | str | None = None
    message: str | None = None


def success(data: JSONDict | None = None) -> ActionResult:
    return ActionResult(ok=True, data=data or {})


def error(code: str, message: str, *, error_code: str | ErrorCode | None = None) -> ActionResult:
    canonical = canonical_error_code(error_code or code)
    return ActionResult(ok=False, error=code, error_code=canonical, message=message)


def attach_contract_fields(result: JSONDict, command: str) -> JSONDict:
    payload = dict(result)
    payload.setdefault("schema_version", SCHEMA_VERSION)
    payload.setdefault("command", command)
    if payload.get("ok") is False:
        payload.setdefault("error", "runtime_error")
        payload.setdefault("message", "Unknown runtime error")
    return payload
