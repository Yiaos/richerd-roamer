"""JSON output formatting utilities."""

from typing import Any


def success(**kwargs: Any) -> dict[str, Any]:
    """Create a success response dict."""
    return {"ok": True, **kwargs}


def error(code: str, message: str, **kwargs: Any) -> dict[str, Any]:
    """Create an error response dict."""
    return {"ok": False, "error": code, "message": message, **kwargs}
