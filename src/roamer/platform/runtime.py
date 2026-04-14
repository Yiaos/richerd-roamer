"""Runtime helpers for plugin action execution."""

from typing import Any

from roamer.platform.plugin_registry import registry


def run_action(action_name: str, **kwargs: Any) -> dict[str, Any]:
    """Run one action through the global registry."""
    return registry.run(action_name, **kwargs)
