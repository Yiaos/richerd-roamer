"""Plugin action registry and dispatcher."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

from roamer.platform.contract import ErrorCode
from roamer.platform.logging import (
    current_request_id,
    log_event,
    log_transcripts_enabled,
    request_context,
)
from roamer.platform.output import error

ActionHandler = Callable[..., dict[str, Any]]
_TEXT_KEYS = {"text", "content", "input", "message", "prompt", "command_text"}


class PluginRegistry:
    """Registry for executable plugin actions."""

    def __init__(self) -> None:
        self._actions: dict[str, ActionHandler] = {}

    def register(self, action_name: str, handler: ActionHandler) -> None:
        """Register one action handler."""
        if action_name in self._actions:
            raise ValueError(f"Action already registered: {action_name}")
        self._actions[action_name] = handler

    def run(self, action_name: str, **kwargs: Any) -> dict[str, Any]:
        """Run a registered action by name."""
        if current_request_id() is None:
            with request_context(uuid.uuid4().hex[:12]):
                return self._run_with_tracing(action_name, **kwargs)
        return self._run_with_tracing(action_name, **kwargs)

    def _run_with_tracing(self, action_name: str, **kwargs: Any) -> dict[str, Any]:
        """Run an action and emit structured lifecycle logs."""
        started_at = time.monotonic()
        log_event(
            "action",
            "action.start",
            action=action_name,
            args=_safe_log_value(kwargs),
        )
        handler = self._actions.get(action_name)
        if handler is None:
            result = error(
                "action_not_found",
                f"Unknown action: {action_name}",
                error_code=ErrorCode.ACTION_NOT_FOUND,
                action=action_name,
            )
            log_event(
                "action",
                "action.done",
                action=action_name,
                ok=False,
                error_code=result.get("error_code"),
                duration_ms=_elapsed_ms(started_at),
            )
            return result
        try:
            result = handler(**kwargs)
        except Exception as exc:
            log_event(
                "action",
                "action.exception",
                action=action_name,
                exception_type=exc.__class__.__name__,
                message=str(exc),
                duration_ms=_elapsed_ms(started_at),
                level="ERROR",
            )
            raise
        log_event(
            "action",
            "action.done",
            action=action_name,
            ok=bool(result.get("ok", False)) if isinstance(result, dict) else False,
            error_code=result.get("error_code") if isinstance(result, dict) else None,
            duration_ms=_elapsed_ms(started_at),
        )
        return result

    def list_actions(self) -> list[str]:
        """List registered action names."""
        return sorted(self._actions.keys())

    def remove(self, action_name: str) -> None:
        """Remove one action handler if present."""
        self._actions.pop(action_name, None)


def _elapsed_ms(started_at: float) -> float:
    return round((time.monotonic() - started_at) * 1000, 3)


def _safe_log_value(value: Any, *, key: str = "", depth: int = 0) -> Any:
    """Convert action args into a JSON-friendly log value while preserving text."""
    if key.lower() in _TEXT_KEYS and not log_transcripts_enabled():
        return ""
    if depth >= 4:
        return repr(value)
    if isinstance(value, dict):
        return {
            str(k): _safe_log_value(v, key=str(k), depth=depth + 1)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_log_value(item, key=key, depth=depth + 1) for item in value]
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


registry = PluginRegistry()
