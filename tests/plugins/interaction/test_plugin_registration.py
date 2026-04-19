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
