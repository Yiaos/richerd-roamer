"""Command result helpers compatible with the legacy CLI contract."""

from __future__ import annotations

from roamerd.contracts.errors import SCHEMA_VERSION, canonical_error_code
from roamerd.events.base import JSONDict, JSONValue


def success(**kwargs: JSONValue) -> JSONDict:
    payload: JSONDict = {"ok": True, "schema_version": SCHEMA_VERSION}
    payload.update(kwargs)
    return payload


def error(
    code: str,
    message: str,
    *,
    error_code: str | None = None,
    **kwargs: JSONValue,
) -> JSONDict:
    payload: JSONDict = {
        "ok": False,
        "error": code,
        "message": message,
        "error_code": error_code or canonical_error_code(code),
        "schema_version": SCHEMA_VERSION,
    }
    payload.update(kwargs)
    return payload


def attach_contract_fields(result: JSONDict, command: str) -> JSONDict:
    payload = dict(result)
    payload.setdefault("schema_version", SCHEMA_VERSION)
    payload.setdefault("command", command)
    if payload.get("ok") is False:
        payload.setdefault("error", "runtime_error")
        payload.setdefault("message", "Unknown runtime error")
    return payload
