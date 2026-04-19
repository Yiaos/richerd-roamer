"""Motion plugin registration."""

from collections.abc import Callable
from typing import Any

from roamer.platform.contract import ErrorCode
from roamer.platform.output import error
from roamer.platform.plugin_registry import PluginRegistry
from roamer.plugins.motion.actions.goto import MotionGotoAction
from roamer.plugins.motion.actions.home import MotionHomeAction
from roamer.plugins.motion.actions.locate import MotionLocateAction
from roamer.plugins.motion.actions.position import MotionPositionAction
from roamer.plugins.motion.actions.status import MotionStatusAction


def _lazy_runner(
    action_cls: Callable[[dict[str, Any]], Any],
    config: dict[str, Any],
) -> Callable[..., dict[str, Any]]:
    """Create lazy action runner to avoid eager initialization."""

    def _run(**kwargs: Any) -> dict[str, Any]:
        try:
            return action_cls(config).run(**kwargs)
        except ValueError as exc:
            return error(
                "config_invalid",
                str(exc),
                error_code=ErrorCode.CONFIG_INVALID,
            )

    return _run


def register(registry: PluginRegistry, config: dict[str, Any]) -> None:
    """Register motion actions into plugin registry."""
    registry.register("motion.status", _lazy_runner(MotionStatusAction, config))
    registry.register("motion.position", _lazy_runner(MotionPositionAction, config))
    registry.register("motion.locate", _lazy_runner(MotionLocateAction, config))
    registry.register("motion.home", _lazy_runner(MotionHomeAction, config))
    registry.register("motion.goto", _lazy_runner(MotionGotoAction, config))
