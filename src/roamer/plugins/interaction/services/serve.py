"""Long-running Roamer serve runtime."""

from __future__ import annotations

import socket
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

    def prewarm(self) -> dict[str, Any]:
        """Initialize reusable daemon state.

        Current P1 keeps heavy driver loading lazy because ListenCapability already caches
        drivers inside the long-running process once constructed by a request. The hook is
        explicit so ASR/VAD prewarming can become real without changing the IPC contract.
        """
        return success(prewarmed=True)

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
            return success(ready=True, registered=self._registered, served_by="daemon")
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
    runtime.prewarm()
    path = Path(socket_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(path))
        server.listen(5)
        while True:
            conn, _ = server.accept()
            with conn:
                request = read_request(conn)
                response = runtime.handle(request) if request.get("ok", True) else request
                write_response(conn, response)
