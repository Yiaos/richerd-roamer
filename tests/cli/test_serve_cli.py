"""CLI tests for roamer serve."""

import json

from click.testing import CliRunner

from roamer.cli.main import main


def test_serve_ping_success(monkeypatch) -> None:
    monkeypatch.setattr(
        "roamer.cli.main.request_via_socket",
        lambda socket_path, payload, timeout_sec: {"ok": True, "pong": True, "served_by": "daemon"},
    )

    result = CliRunner().invoke(main, ["serve", "ping"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["pong"] is True
    assert payload["command"] == "serve.ping"


def test_serve_ping_unavailable(monkeypatch) -> None:
    from roamer.plugins.interaction.services.ipc import IpcUnavailableError

    def _raise(*args, **kwargs):
        raise IpcUnavailableError("missing socket")

    monkeypatch.setattr("roamer.cli.main.request_via_socket", _raise)

    result = CliRunner().invoke(main, ["serve", "ping"])

    assert result.exit_code == 11
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error_code"] == "serve.unavailable"
    assert payload["command"] == "serve.ping"


def test_converse_cli_uses_daemon_when_available(monkeypatch) -> None:
    calls = []

    def _request(socket_path, payload, timeout_sec):
        calls.append(payload)
        return {"ok": True, "completed": True, "served_by": "daemon", "turns": []}

    monkeypatch.setattr("roamer.cli.main.request_via_socket", _request)

    result = CliRunner().invoke(main, ["converse", "--no-wakeword", "--max-turns", "1"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["served_by"] == "daemon"
    assert payload["command"] == "converse"
    assert calls[0]["command"] == "converse"


def test_converse_cli_falls_back_when_daemon_unavailable(monkeypatch, tmp_path) -> None:
    from roamer.plugins.interaction.services.ipc import IpcUnavailableError

    config = tmp_path / "config.yaml"
    config.write_text(
        "\n".join(
            [
                "serve:",
                "  enabled: true",
                "  fallback_to_cli: true",
                "converse:",
                "  wakeword:",
                "    enabled: false",
            ]
        )
    )

    def _raise(*args, **kwargs):
        raise IpcUnavailableError("missing socket")

    monkeypatch.setattr("roamer.cli.main.request_via_socket", _raise)
    monkeypatch.setattr(
        "roamer.cli.main.run_action",
        lambda action_name, **kwargs: {"ok": True, "completed": True, "turns": []},
    )

    result = CliRunner().invoke(main, ["--config", str(config), "converse"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["served_by"] == "cli"
    assert payload["command"] == "converse"


def test_converse_cli_reports_serve_unavailable_when_fallback_disabled(
    monkeypatch, tmp_path
) -> None:
    from roamer.plugins.interaction.services.ipc import IpcUnavailableError

    config = tmp_path / "config.yaml"
    config.write_text("serve:\n  enabled: true\n  fallback_to_cli: false\n")

    def _raise(*args, **kwargs):
        raise IpcUnavailableError("missing socket")

    monkeypatch.setattr("roamer.cli.main.request_via_socket", _raise)

    result = CliRunner().invoke(main, ["--config", str(config), "converse", "--no-wakeword"])

    assert result.exit_code == 11
    payload = json.loads(result.output)
    assert payload["error_code"] == "serve.unavailable"
    assert payload["served_by"] == "none"


def test_converse_cli_does_not_fallback_after_daemon_request_timeout(
    monkeypatch, tmp_path
) -> None:
    from roamer.plugins.interaction.services.ipc import IpcRequestTimeoutError

    config = tmp_path / "config.yaml"
    config.write_text(
        "\n".join(
            [
                "serve:",
                "  enabled: true",
                "  fallback_to_cli: true",
                "converse:",
                "  wakeword:",
                "    enabled: false",
            ]
        )
    )

    def _raise(*args, **kwargs):
        raise IpcRequestTimeoutError("read timed out")

    fallback_calls = []
    monkeypatch.setattr("roamer.cli.main.request_via_socket", _raise)
    monkeypatch.setattr(
        "roamer.cli.main.run_action",
        lambda action_name, **kwargs: fallback_calls.append(action_name) or {"ok": True},
    )

    result = CliRunner().invoke(main, ["--config", str(config), "converse"])

    assert result.exit_code == 12
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error_code"] == "serve.timeout"
    assert payload["served_by"] == "none"
    assert fallback_calls == []


def test_converse_cli_does_not_fallback_after_daemon_protocol_error(
    monkeypatch, tmp_path
) -> None:
    from roamer.plugins.interaction.services.ipc import IpcProtocolError

    config = tmp_path / "config.yaml"
    config.write_text(
        "\n".join(
            [
                "serve:",
                "  enabled: true",
                "  fallback_to_cli: true",
                "converse:",
                "  wakeword:",
                "    enabled: false",
            ]
        )
    )

    def _raise(*args, **kwargs):
        raise IpcProtocolError("broken pipe")

    fallback_calls = []
    monkeypatch.setattr("roamer.cli.main.request_via_socket", _raise)
    monkeypatch.setattr(
        "roamer.cli.main.run_action",
        lambda action_name, **kwargs: fallback_calls.append(action_name) or {"ok": True},
    )

    result = CliRunner().invoke(main, ["--config", str(config), "converse"])

    assert result.exit_code == 11
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error_code"] == "serve.request_failed"
    assert payload["served_by"] == "none"
    assert fallback_calls == []


def test_serve_help_describes_prepare_and_legacy_prewarm_honestly() -> None:
    result = CliRunner().invoke(main, ["serve", "--help"])

    assert result.exit_code == 0
    assert "--prepare" in result.output
    assert "Prepare daemon action cache" in result.output
    assert "--prewarm" in result.output
    assert "does not preload heavy" in result.output
