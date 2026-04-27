"""Unix-socket IPC helpers for Roamer serve."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any

from roamer.platform.contract import ErrorCode
from roamer.platform.output import error


class IpcClientError(RuntimeError):
    """Raised when the serve IPC client cannot complete a request."""


def request_via_socket(
    socket_path: str,
    payload: dict[str, Any],
    *,
    timeout_sec: float,
) -> dict[str, Any]:
    """Send one newline-delimited JSON request to a Unix socket."""
    path = Path(socket_path).expanduser()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout_sec)
            client.connect(str(path))
            client.sendall(json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n")
            raw = _readline(client)
    except OSError as exc:
        raise IpcClientError(str(exc)) from exc

    if not raw:
        raise IpcClientError("Empty response from roamer serve")

    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IpcClientError(f"Invalid response from roamer serve: {exc}") from exc

    if not isinstance(decoded, dict):
        raise IpcClientError("Invalid response from roamer serve: expected object")
    return decoded


def read_request(conn: socket.socket) -> dict[str, Any]:
    """Read and decode one newline-delimited JSON request from a connection."""
    try:
        raw = _readline(conn)
    except IpcClientError as exc:
        return error(
            "serve_request_failed",
            str(exc),
            error_code=ErrorCode.SERVE_REQUEST_FAILED,
        )
    if not raw:
        return error(
            "serve_request_failed",
            "Empty serve request",
            error_code=ErrorCode.SERVE_REQUEST_FAILED,
        )
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return error(
            "serve_request_failed",
            f"Invalid serve request JSON: {exc}",
            error_code=ErrorCode.SERVE_REQUEST_FAILED,
        )
    if not isinstance(decoded, dict):
        return error(
            "serve_request_failed",
            "Invalid serve request: expected object",
            error_code=ErrorCode.SERVE_REQUEST_FAILED,
        )
    return decoded


def write_response(conn: socket.socket, response: dict[str, Any]) -> None:
    """Write one newline-delimited JSON response to a connection."""
    conn.sendall(json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n")


def _readline(sock: socket.socket, max_bytes: int = 65536) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = sock.recv(1)
        if not chunk:
            break
        if chunk == b"\n":
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:
            raise IpcClientError("Serve request exceeded maximum size")
    return b"".join(chunks)
