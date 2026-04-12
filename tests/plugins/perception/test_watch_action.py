"""Tests for perception.watch plugin action."""

from unittest.mock import MagicMock

from roamer.platform.plugin_registry import PluginRegistry
from roamer.plugins.perception.actions.watch import WatchAction
from roamer.plugins.perception.plugin import register


def test_watch_action_uses_explicit_arguments() -> None:
    """Watch action passes explicit output/size to the driver."""
    driver = MagicMock()
    driver.snap.return_value = {"ok": True, "path": "/tmp/x.jpg", "width": 640, "height": 480}

    action = WatchAction(config={"fswebcam": {"width": 1280, "height": 720}}, driver=driver)
    result = action.run(output="/tmp/x.jpg", width=640, height=480)

    driver.snap.assert_called_once_with("/tmp/x.jpg", 640, 480)
    assert result["ok"] is True


def test_watch_action_uses_defaults_from_config() -> None:
    """Watch action derives missing width/height from fswebcam config."""
    driver = MagicMock()
    driver.snap.return_value = {
        "ok": True,
        "path": "/tmp/default.jpg",
        "width": 1920,
        "height": 1080,
    }

    action = WatchAction(config={"fswebcam": {"width": 1920, "height": 1080}}, driver=driver)
    action.run(output="/tmp/default.jpg")

    driver.snap.assert_called_once_with("/tmp/default.jpg", 1920, 1080)


def test_perception_plugin_registers_watch_action() -> None:
    """Plugin register() wires watch action into registry."""
    registry = PluginRegistry()

    register(registry, config={"fswebcam": {"width": 1280, "height": 720}})
    registered = registry.list_actions()

    assert "watch" in registered
