"""Tests for motion plugin registration behavior."""

from unittest.mock import patch

from roamer.platform.plugin_registry import PluginRegistry
from roamer.plugins.motion.plugin import register


def test_motion_register_does_not_eagerly_construct_unrelated_actions() -> None:
    registry = PluginRegistry()

    with patch(
        "roamer.plugins.motion.plugin.MotionGotoAction",
        side_effect=RuntimeError("boom"),
    ) as mock_goto:
        with patch("roamer.plugins.motion.plugin.MotionStatusAction") as mock_status_cls:
            mock_status = mock_status_cls.return_value
            mock_status.run.return_value = {"ok": True, "status": "idle"}

            register(registry, config={"drivers": {"motion": "valetudo"}})
            result = registry.run("motion.status")

    assert result["ok"] is True
    assert result["status"] == "idle"
    mock_goto.assert_not_called()
    mock_status_cls.assert_called_once()
