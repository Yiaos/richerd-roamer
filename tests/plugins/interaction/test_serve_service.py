"""Tests for Roamer serve runtime and IPC."""

import socket
import threading
import time
from pathlib import Path

from roamer.platform.contract import ErrorCode
from roamer.plugins.interaction.services.ipc import (
    IpcRequestTimeoutError,
    read_request,
    request_via_socket,
    write_response,
)
from roamer.plugins.interaction.services.serve import RoamerServeRuntime, serve_forever


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


def test_serve_runtime_prepare_registers_and_caches_listen_action(monkeypatch) -> None:
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
    result = runtime.prepare()
    status = runtime.handle({"command": "status", "args": {}})

    assert result["ok"] is True
    assert result["prepared"] is True
    assert result["registered"] is True
    assert result["listen_action_cached"] is True
    assert status["registered"] is True
    assert status["listen_action_cached"] is True
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


def test_serve_runtime_prewarm_alias_uses_prepare(monkeypatch) -> None:
    runtime = RoamerServeRuntime({})
    called = []

    monkeypatch.setattr(runtime, "prepare", lambda: called.append("prepare") or {"ok": True})

    result = runtime.prewarm()

    assert result["ok"] is True
    assert called == ["prepare"]


def test_ipc_request_timeout_after_send_is_not_unavailable(tmp_path) -> None:
    socket_path = Path("/tmp") / f"roamer-{id(tmp_path)}.sock"
    ready = threading.Event()
    done = threading.Event()

    def _server() -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(socket_path))
            server.listen(1)
            ready.set()
            conn, _ = server.accept()
            with conn:
                assert conn.recv(1024)
                done.wait(timeout=1)

    thread = threading.Thread(target=_server, daemon=True)
    socket_path.unlink(missing_ok=True)
    thread.start()
    ready.wait(timeout=1)

    try:
        try:
            request_via_socket(str(socket_path), {"command": "ping", "args": {}}, timeout_sec=0.05)
            raise AssertionError("request_via_socket should time out")
        except IpcRequestTimeoutError as exc:
            assert "Timed out" in str(exc)
    finally:
        done.set()
        thread.join(timeout=1)
        socket_path.unlink(missing_ok=True)


def _wait_for_serve_socket(socket_path: Path) -> None:
    last_error: Exception | None = None
    for _ in range(100):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(0.1)
                client.connect(str(socket_path))
                return
        except OSError as exc:
            last_error = exc
        time.sleep(0.01)
    raise AssertionError(f"serve socket did not become ready: {last_error}")


def test_serve_forever_rejects_second_request_while_busy(tmp_path) -> None:
    socket_path = Path("/tmp") / f"roamer-{id(tmp_path)}.sock"
    first_started = threading.Event()
    release_first = threading.Event()

    class _Runtime:
        def prepare(self):
            return {"ok": True}

        def handle(self, request):
            if request["command"] == "converse":
                first_started.set()
                release_first.wait(timeout=1)
                return {"ok": True, "served_by": "daemon"}
            return {"ok": True}

    socket_path.unlink(missing_ok=True)
    server = threading.Thread(
        target=serve_forever,
        args=({"serve": {"request_timeout_sec": 1.0}}, str(socket_path)),
        kwargs={"runtime": _Runtime()},
        daemon=True,
    )
    server.start()
    _wait_for_serve_socket(socket_path)

    first = threading.Thread(
        target=request_via_socket,
        args=(str(socket_path), {"command": "converse", "args": {}}),
        kwargs={"timeout_sec": 2.0},
        daemon=True,
    )
    first.start()
    assert first_started.wait(timeout=1)

    busy = request_via_socket(
        str(socket_path),
        {"command": "converse", "args": {}},
        timeout_sec=0.5,
    )

    release_first.set()
    first.join(timeout=1)
    assert busy["ok"] is False
    assert busy["error_code"] == ErrorCode.SERVE_UNAVAILABLE
    assert busy["served_by"] == "daemon"
    socket_path.unlink(missing_ok=True)


def test_serve_forever_recovers_after_runtime_exception(tmp_path) -> None:
    socket_path = Path("/tmp") / f"roamer-{id(tmp_path)}.sock"
    calls = 0

    class _Runtime:
        def prepare(self):
            return {"ok": True}

        def handle(self, request):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("boom")
            return {"ok": True, "served_by": "daemon", "calls": calls}

    socket_path.unlink(missing_ok=True)
    server = threading.Thread(
        target=serve_forever,
        args=({"serve": {"request_timeout_sec": 1.0}}, str(socket_path)),
        kwargs={"runtime": _Runtime()},
        daemon=True,
    )
    server.start()
    _wait_for_serve_socket(socket_path)

    first = request_via_socket(str(socket_path), {"command": "ping", "args": {}}, timeout_sec=1.0)
    second = request_via_socket(str(socket_path), {"command": "ping", "args": {}}, timeout_sec=1.0)

    assert first["ok"] is False
    assert first["error_code"] == ErrorCode.SERVE_REQUEST_FAILED
    assert second["ok"] is True
    assert second["calls"] == 2
    socket_path.unlink(missing_ok=True)
