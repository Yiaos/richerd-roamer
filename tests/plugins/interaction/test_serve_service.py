"""Tests for Roamer serve runtime and IPC."""

import socket
import threading

from roamer.plugins.interaction.services.ipc import read_request, write_response
from roamer.plugins.interaction.services.serve import RoamerServeRuntime


def test_serve_runtime_ping() -> None:
    runtime = RoamerServeRuntime({})

    result = runtime.handle({"command": "ping", "args": {}})

    assert result["ok"] is True
    assert result["pong"] is True
    assert result["served_by"] == "daemon"


def test_serve_runtime_rejects_unknown_command() -> None:
    runtime = RoamerServeRuntime({})

    result = runtime.handle({"command": "missing", "args": {}})

    assert result["ok"] is False
    assert result["error_code"] == "serve.request_failed"
    assert result["served_by"] == "daemon"


def test_serve_runtime_dispatches_converse(monkeypatch) -> None:
    runtime = RoamerServeRuntime({})
    calls = []

    monkeypatch.setattr(runtime, "ensure_registered", lambda: calls.append("registered"))
    monkeypatch.setattr(
        "roamer.plugins.interaction.services.serve.run_action",
        lambda action_name, **kwargs: {"ok": True, "action": action_name, "kwargs": kwargs},
    )

    result = runtime.handle(
        {
            "command": "converse",
            "args": {"no_wakeword": True, "timeout": 2.5},
        }
    )

    assert calls == ["registered"]
    assert result["ok"] is True
    assert result["action"] == "converse"
    assert result["kwargs"] == {"no_wakeword": True, "timeout": 2.5}
    assert result["served_by"] == "daemon"


def test_ipc_read_write_round_trip() -> None:
    left, right = socket.socketpair()
    try:
        left.sendall(b'{"command":"ping","args":{}}\n')
        request = read_request(right)
        assert request == {"command": "ping", "args": {}}

        write_response(right, {"ok": True, "pong": True})
        assert left.recv(1024) == b'{"ok": true, "pong": true}\n'
    finally:
        left.close()
        right.close()


def test_ipc_invalid_json_returns_error() -> None:
    left, right = socket.socketpair()
    try:
        left.sendall(b'not-json\n')
        request = read_request(right)
        assert request["ok"] is False
        assert request["error_code"] == "serve.request_failed"
    finally:
        left.close()
        right.close()


def test_serve_runtime_reuses_listen_action(monkeypatch) -> None:
    listen_instances = []

    class _ListenAction:
        def __init__(self, config):
            listen_instances.append(config)

        def run(self, **kwargs):
            return {"ok": True, "text": ""}

    monkeypatch.setattr(
        "roamer.plugins.interaction.services.serve.ListenAction",
        _ListenAction,
    )

    runtime = RoamerServeRuntime({"converse": {"wakeword": {"enabled": False}}})
    first = runtime.handle({"command": "converse", "args": {"no_wakeword": True}})
    second = runtime.handle({"command": "converse", "args": {"no_wakeword": True}})

    assert first["ok"] is True
    assert second["ok"] is True
    assert len(listen_instances) == 1


def test_serve_runtime_prewarm_registers_and_caches_listen(monkeypatch) -> None:
    listen_instances = []

    class _ListenAction:
        def __init__(self, config):
            listen_instances.append(config)

        def run(self, **kwargs):
            return {"ok": True, "text": ""}

    monkeypatch.setattr(
        "roamer.plugins.interaction.services.serve.ListenAction",
        _ListenAction,
    )

    runtime = RoamerServeRuntime({})
    result = runtime.prewarm()
    status = runtime.handle({"command": "status", "args": {}})

    assert result["ok"] is True
    assert result["registered"] is True
    assert result["listen_cached"] is True
    assert status["registered"] is True
    assert status["listen_cached"] is True
    assert len(listen_instances) == 1


def test_ipc_oversized_request_returns_error() -> None:
    left, right = socket.socketpair()
    sender = threading.Thread(target=left.sendall, args=(b"x" * 65537 + b"\n",))
    try:
        sender.start()
        request = read_request(right)
        assert request["ok"] is False
        assert request["error_code"] == "serve.request_failed"
        assert "maximum size" in request["message"]
    finally:
        left.close()
        right.close()
        sender.join(timeout=1)
