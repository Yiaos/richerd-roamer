"""JSON output formatting utilities."""

from typing import Any

from roamer.platform.contract import SCHEMA_VERSION, canonical_error_code


def success(**kwargs: Any) -> dict[str, Any]:
    """Create a success response dict."""
    return {"ok": True, "schema_version": SCHEMA_VERSION, **kwargs}


def error(
    code: str,
    message: str,
    *,
    error_code: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Create an error response dict."""
    return {
        "ok": False,
        "error": code,
        "message": message,
        "error_code": error_code or canonical_error_code(code),
        "schema_version": SCHEMA_VERSION,
        **kwargs,
    }


def attach_contract_fields(result: dict[str, Any], command: str) -> dict[str, Any]:
    """Attach standard contract metadata to a payload."""
    payload = dict(result)
    payload.setdefault("schema_version", SCHEMA_VERSION)
    payload.setdefault("command", command)

    if payload.get("ok") is False:
        payload.setdefault("error", "runtime_error")
        payload.setdefault("message", "Unknown runtime error")

    return payload
