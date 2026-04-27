"""Long-running Roamer serve runtime."""

from __future__ import annotations

import os
import socket
import threading
from pathlib import Path
from typing import Any

from roamer.platform.contract import ErrorCode
from roamer.platform.output import error, success
from roamer.platform.plugin_registry import registry
from roamer.platform.runtime import run_action
from roamer.plugins.interaction.actions.listen import ListenAction
from roamer.plugins.interaction.plugin import register as register_interaction_plugin
from roamer.plugins.interaction.services.ipc import read_request, write_response


class RoamerServeRuntime:
    """Reusable runtime for daemon-backed Roamer commands."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self._registered = False
        self._listen_action: ListenAction | None = None

    def ensure_registered(self) -> None:
        """Register interaction actions once for this process."""
        if self._registered:
            return
        for action_name in (
            "listen",
            "speak",
            "remind",
            "converse",
            "audio.record",
            "audio.play",
            "bt.status",
            "bt.connect",
            "init",
        ):
            registry.remove(action_name)
        register_interaction_plugin(registry, self.config)
        if self._listen_action is None:
            self._listen_action = ListenAction(self.config)
        registry.remove("listen")
        registry.register("listen", self._listen_action.run)
        self._registered = True

    def prepare(self) -> dict[str, Any]:
        """Prepare reusable daemon state without loading heavy speech models.

        P1 keeps ASR/VAD/TTS model loading lazy. The daemon registers actions and
        caches the listen action object so later requests reuse in-process state,
        but this does not claim FunASR/Silero/TTS models are preloaded.
        """
        self.ensure_registered()
        return success(
            prepared=True,
            registered=self._registered,
            listen_action_cached=self._listen_action is not None,
        )

    def prewarm(self) -> dict[str, Any]:
        """Backward-compatible alias for older --prewarm callers."""
        return self.prepare()

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle one decoded serve request."""
        command = str(request.get("command") or "")
        args = request.get("args") or {}
        if not isinstance(args, dict):
            return error(
                "serve_request_failed",
                "Serve request args must be an object",
                error_code=ErrorCode.SERVE_REQUEST_FAILED,
                served_by="daemon",
            )

        if command == "ping":
            return success(pong=True, served_by="daemon")
        if command == "status":
            return success(
                alive=True,
                ready=True,
                registered=self._registered,
                listen_action_cached=self._listen_action is not None,
                served_by="daemon",
            )
        if command == "converse":
            self.ensure_registered()
            result = run_action("converse", **args)
            result["served_by"] = "daemon"
            return result

        return error(
            "serve_request_failed",
            f"Unsupported serve command: {command or '<empty>'}",
            error_code=ErrorCode.SERVE_REQUEST_FAILED,
            served_by="daemon",
        )


def serve_forever(
    config: dict[str, Any],
    socket_path: str,
    *,
    runtime: RoamerServeRuntime | None = None,
) -> None:
    """Run the blocking Unix-socket serve loop."""
    runtime = runtime or RoamerServeRuntime(config)
    runtime.prepare()
    path = Path(socket_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)

    busy_lock = threading.Lock()

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        old_umask = os.umask(0o077)
        try:
            server.bind(str(path))
        finally:
            os.umask(old_umask)
        path.chmod(0o600)
        server.listen(5)
        while True:
            conn, _ = server.accept()
            if not busy_lock.acquire(blocking=False):
                _write_busy_response(conn)
                conn.close()
                continue

            worker = threading.Thread(
                target=_handle_connection,
                args=(conn, runtime, config, busy_lock),
                daemon=True,
            )
            worker.start()


def _handle_connection(
    conn: socket.socket,
    runtime: RoamerServeRuntime,
    config: dict[str, Any],
    busy_lock: threading.Lock,
) -> None:
    try:
        with conn:
            conn.settimeout(float(config.get("serve", {}).get("request_timeout_sec", 60.0)))
            try:
                request = read_request(conn)
                response = runtime.handle(request) if request.get("ok", True) else request
            except Exception as exc:
                response = error(
                    "serve_request_failed",
                    f"Serve request failed: {exc}",
                    error_code=ErrorCode.SERVE_REQUEST_FAILED,
                    served_by="daemon",
                )
            try:
                write_response(conn, response)
            except OSError:
                pass
    finally:
        busy_lock.release()


def _write_busy_response(conn: socket.socket) -> None:
    try:
        with conn:
            write_response(
                conn,
                error(
                    "serve_busy",
                    "Roamer serve is busy handling another request",
                    error_code=ErrorCode.SERVE_UNAVAILABLE,
                    served_by="daemon",
                ),
            )
    except OSError:
        pass
