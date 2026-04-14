"""Tests for core plugin registry runtime dispatch."""

from roamer.platform.plugin_registry import PluginRegistry


def test_register_and_run_action() -> None:
    """Registry runs a registered action handler."""
    registry = PluginRegistry()

    def _watch_action(*, output: str | None = None, width: int = 1280) -> dict:
        return {"ok": True, "output": output, "width": width}

    registry.register("watch", _watch_action)
    result = registry.run("watch", output="/tmp/a.jpg", width=640)

    assert result["ok"] is True
    assert result["output"] == "/tmp/a.jpg"
    assert result["width"] == 640


def test_run_unknown_action_returns_error_payload() -> None:
    """Unknown action returns deterministic error payload."""
    registry = PluginRegistry()

    result = registry.run("unknown.action")

    assert result["ok"] is False
    assert result["error"] == "action_not_found"
    assert result["message"]
    assert result["error_code"]


def test_register_duplicate_action_raises() -> None:
    """Registering the same action twice is blocked."""
    registry = PluginRegistry()

    registry.register("watch", lambda **_: {"ok": True})

    try:
        registry.register("watch", lambda **_: {"ok": True})
    except ValueError as exc:
        assert "watch" in str(exc)
    else:
        raise AssertionError("Expected ValueError for duplicate action registration")
