"""Tests for local intent action registration in converse."""

from unittest.mock import patch

from roamer.platform.plugin_registry import registry
from roamer.plugins.interaction.capabilities.converse import ConverseCapability


def test_converse_registers_perception_actions_for_local_intents() -> None:
    registry.remove("sense")
    capability = ConverseCapability({})

    with patch(
        "roamer.plugins.interaction.capabilities.converse.register_perception_plugin"
    ) as mock_perception, patch(
        "roamer.plugins.interaction.capabilities.converse.register_motion_plugin"
    ) as mock_motion:
        mock_perception.side_effect = lambda reg, config: reg.register(
            "sense", lambda **kwargs: {"ok": True, "action": "sense"}
        )
        mock_motion.side_effect = lambda reg, config: None

        capability._ensure_local_intent_actions_registered()
        result = registry.run("sense")

    assert result == {"ok": True, "action": "sense"}
    mock_perception.assert_called_once()
    mock_motion.assert_called_once()
