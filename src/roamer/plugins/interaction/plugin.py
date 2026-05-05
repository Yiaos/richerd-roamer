"""Interaction plugin registration."""

from collections.abc import Callable
from typing import Any

from roamer.platform.contract import ErrorCode
from roamer.platform.errors import RoamerError
from roamer.platform.output import error
from roamer.platform.plugin_registry import PluginRegistry
from roamer.plugins.interaction.actions.audio_play import AudioPlayAction
from roamer.plugins.interaction.actions.audio_record import AudioRecordAction
from roamer.plugins.interaction.actions.bt_connect import BtConnectAction
from roamer.plugins.interaction.actions.bt_status import BtStatusAction
from roamer.plugins.interaction.actions.converse import ConverseAction
from roamer.plugins.interaction.actions.listen import ListenAction
from roamer.plugins.interaction.actions.remind import RemindAction
from roamer.plugins.interaction.actions.speak import SpeakAction
from roamer.plugins.interaction.actions.wake import WakeAction
from roamer.plugins.interaction.capabilities.init import InitCapability


def _lazy_runner(
    action_cls: Callable[[dict[str, Any]], Any],
    config: dict[str, Any],
) -> Callable[..., dict[str, Any]]:
    """Create a lazy action runner to avoid eager plugin-side initialization."""

    def _run(**kwargs: Any) -> dict[str, Any]:
        try:
            return action_cls(config).run(**kwargs)
        except ValueError as exc:
            return error(
                "config_invalid",
                str(exc),
                error_code=ErrorCode.CONFIG_INVALID,
            )
        except RoamerError as exc:
            canonical_code = getattr(exc, "code", "runtime_error")
            legacy_code = canonical_code.replace(".", "_")
            return error(
                legacy_code,
                str(exc),
                error_code=canonical_code,
            )

    return _run


def register(registry: PluginRegistry, config: dict[str, Any]) -> None:
    """Register interaction actions into plugin registry."""
    registry.register("listen", _lazy_runner(ListenAction, config))
    registry.register("remind", _lazy_runner(RemindAction, config))
    registry.register("speak", _lazy_runner(SpeakAction, config))
    registry.register("converse", _lazy_runner(ConverseAction, config))
    registry.register("wake", _lazy_runner(WakeAction, config))
    registry.register("audio.record", _lazy_runner(AudioRecordAction, config))
    registry.register("audio.play", _lazy_runner(AudioPlayAction, config))
    registry.register("bt.status", _lazy_runner(BtStatusAction, config))
    registry.register("bt.connect", _lazy_runner(BtConnectAction, config))
    registry.register("init", _lazy_runner(InitCapability, config))
