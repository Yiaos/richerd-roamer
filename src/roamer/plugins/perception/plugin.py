"""Perception plugin registration."""

from collections.abc import Callable
from typing import Any

from roamer.platform.plugin_registry import PluginRegistry
from roamer.plugins.perception.actions.sense import SenseAction
from roamer.plugins.perception.actions.watch import WatchAction


def _lazy_runner(
    action_cls: Callable[[dict[str, Any]], Any],
    config: dict[str, Any],
) -> Callable[..., dict[str, Any]]:
    """Create a lazy action runner to avoid eager plugin-side initialization."""

    def _run(**kwargs: Any) -> dict[str, Any]:
        return action_cls(config).run(**kwargs)

    return _run


def register(registry: PluginRegistry, config: dict[str, Any]) -> None:
    """Register perception actions into plugin registry."""
    registry.register("watch", _lazy_runner(WatchAction, config))
    registry.register("sense", _lazy_runner(SenseAction, config))
