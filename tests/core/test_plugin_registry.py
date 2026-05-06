"""Tests for core plugin registry runtime dispatch."""

from __future__ import annotations

import json
from pathlib import Path

from roamer.platform.logging import request_context, setup_logging
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


def _read_log_payloads(log_dir: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (log_dir / "roamer.log").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_registry_logs_registered_action_lifecycle(tmp_path: Path) -> None:
    """Newly registered actions automatically emit start and done logs."""
    setup_logging({"logging": {"enabled": True, "dir": str(tmp_path)}})
    registry = PluginRegistry()

    registry.register("custom.echo", lambda *, text: {"ok": True, "text": text})

    result = registry.run("custom.echo", text="完整文本需要记录")

    assert result["ok"] is True
    payloads = _read_log_payloads(tmp_path)
    assert [(p["component"], p["event"]) for p in payloads] == [
        ("action", "action.start"),
        ("action", "action.done"),
    ]
    assert payloads[0]["action"] == "custom.echo"
    assert payloads[0]["args"]["text"] == "完整文本需要记录"
    assert payloads[1]["action"] == "custom.echo"
    assert payloads[1]["ok"] is True
    assert payloads[1]["error_code"] is None
    assert payloads[1]["duration_ms"] >= 0
    assert payloads[0]["request_id"] == payloads[1]["request_id"]


def test_registry_preserves_existing_request_id(tmp_path: Path) -> None:
    """Nested registered actions inherit the active request id."""
    setup_logging({"logging": {"enabled": True, "dir": str(tmp_path)}})
    registry = PluginRegistry()
    registry.register("custom.ok", lambda: {"ok": True})

    with request_context("req-parent"):
        result = registry.run("custom.ok")

    assert result["ok"] is True
    payloads = _read_log_payloads(tmp_path)
    assert [p["request_id"] for p in payloads] == ["req-parent", "req-parent"]


def test_registry_respects_log_transcripts_setting_for_text_args(tmp_path: Path) -> None:
    """Text-like action args are hidden when transcript logging is disabled."""
    setup_logging(
        {
            "logging": {
                "enabled": True,
                "dir": str(tmp_path),
                "log_transcripts": False,
            }
        }
    )
    registry = PluginRegistry()
    registry.register("custom.echo", lambda *, text: {"ok": True, "text": text})

    result = registry.run("custom.echo", text="不要记录全文")

    assert result["ok"] is True
    payloads = _read_log_payloads(tmp_path)
    assert payloads[0]["args"]["text"] == ""


def test_registry_logs_exception_lifecycle(tmp_path: Path) -> None:
    """Registered action exceptions emit an action.exception terminal event."""
    setup_logging({"logging": {"enabled": True, "dir": str(tmp_path)}})
    registry = PluginRegistry()

    def _boom() -> dict:
        raise TimeoutError("command timed out")

    registry.register("custom.boom", _boom)

    try:
        registry.run("custom.boom")
    except TimeoutError:
        pass
    else:
        raise AssertionError("Expected TimeoutError")

    payloads = _read_log_payloads(tmp_path)
    assert [(p["component"], p["event"]) for p in payloads] == [
        ("action", "action.start"),
        ("action", "action.exception"),
    ]
    assert payloads[1]["action"] == "custom.boom"
    assert payloads[1]["exception_type"] == "TimeoutError"
    assert payloads[1]["message"] == "command timed out"
    assert payloads[1]["duration_ms"] >= 0
