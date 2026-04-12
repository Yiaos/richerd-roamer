"""Plugin action registry and dispatcher."""

from collections.abc import Callable
from typing import Any

from roamer.platform.contract import ErrorCode
from roamer.platform.output import error

ActionHandler = Callable[..., dict[str, Any]]


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
        handler = self._actions.get(action_name)
        if handler is None:
            return error(
                "action_not_found",
                f"Unknown action: {action_name}",
                error_code=ErrorCode.ACTION_NOT_FOUND,
                action=action_name,
            )
        return handler(**kwargs)

    def list_actions(self) -> list[str]:
        """List registered action names."""
        return sorted(self._actions.keys())

    def remove(self, action_name: str) -> None:
        """Remove one action handler if present."""
        self._actions.pop(action_name, None)


registry = PluginRegistry()
