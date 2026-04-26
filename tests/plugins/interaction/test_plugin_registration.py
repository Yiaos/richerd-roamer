"""Tests for interaction plugin registration behavior."""

from unittest.mock import MagicMock, patch

from roamer.platform.plugin_registry import PluginRegistry
from roamer.plugins.interaction.plugin import register


def test_interaction_register_does_not_eagerly_construct_unrelated_actions() -> None:
    """bt.status should not require constructing listen action during registration."""
    registry = PluginRegistry()

    with patch(
        "roamer.plugins.interaction.plugin.ListenAction",
        side_effect=RuntimeError("boom"),
    ) as mock_listen:
        bt_status_instance = MagicMock()
        bt_status_instance.run.return_value = {"ok": True, "enabled": True}

        with patch(
            "roamer.plugins.interaction.plugin.BtStatusAction",
            return_value=bt_status_instance,
        ) as mock_bt:
            register(registry, config={"drivers": {"asr": "missing_asr"}})
            result = registry.run("bt.status")

    assert result["ok"] is True
    mock_listen.assert_not_called()
    mock_bt.assert_called_once()


def test_interaction_register_keeps_bt_status_isolated_from_converse() -> None:
    """bt.status should not require constructing converse action during registration."""
    registry = PluginRegistry()

    with patch(
        "roamer.plugins.interaction.plugin.ConverseAction",
        side_effect=RuntimeError("converse-boom"),
    ) as mock_converse:
        bt_status_instance = MagicMock()
        bt_status_instance.run.return_value = {"ok": True, "enabled": True}

        with patch(
            "roamer.plugins.interaction.plugin.BtStatusAction",
            return_value=bt_status_instance,
        ) as mock_bt:
            register(registry, config={"drivers": {"asr": "missing_asr"}})
            result = registry.run("bt.status")

    assert result["ok"] is True
    mock_converse.assert_not_called()
    mock_bt.assert_called_once()


def test_converse_spoken_reminder_dispatches_registered_remind_action() -> None:
    """Converse reminder intent should hit the registered remind action."""
    registry = PluginRegistry()
    import roamer.platform.plugin_registry as registry_module
    import roamer.platform.runtime as runtime_module
    import roamer.plugins.interaction.capabilities.converse as converse_module

    original_registry = registry_module.registry
    registry_module.registry = registry
    runtime_module.registry = registry
    converse_module.registry = registry
    config = {
        "converse": {
            "wakeword": {"enabled": False},
            "intents": [],
            "discord": {"enabled": False},
        }
    }
    calls = []

    def listen_run(**kwargs):
        return {"ok": True, "text": "十秒后提醒我喝水"}

    def remind_run(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "scheduled": True, **kwargs}

    def speak_run(**kwargs):
        return {"ok": True, "played": True}

    try:
        with patch("roamer.plugins.interaction.plugin.ListenAction") as listen_cls:
            with patch("roamer.plugins.interaction.plugin.RemindAction") as remind_cls:
                with patch("roamer.plugins.interaction.plugin.SpeakAction") as speak_cls:
                    listen_cls.return_value.run.side_effect = listen_run
                    remind_cls.return_value.run.side_effect = remind_run
                    speak_cls.return_value.run.side_effect = speak_run

                    register(registry, config=config)
                    result = registry.run(
                        "converse",
                        no_wakeword=True,
                        timeout=0.1,
                        no_sound=True,
                        max_turns=1,
                    )
    finally:
        registry_module.registry = original_registry
        runtime_module.registry = original_registry
        converse_module.registry = original_registry

    assert result["ok"] is True
    turn = result["turns"][0]
    assert turn["action"] == "remind.schedule"
    assert turn["action_result"]["ok"] is True
    assert calls == [{"delay_sec": 10.0, "text": "喝水"}]
