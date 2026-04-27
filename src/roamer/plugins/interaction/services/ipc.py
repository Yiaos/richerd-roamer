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


class IpcUnavailableError(IpcClientError):
    """Raised before a request reaches the serve daemon."""


class IpcRequestTimeoutError(IpcClientError):
    """Raised after a request was sent but no response arrived in time."""


class IpcProtocolError(IpcClientError):
    """Raised after the daemon connection produced an invalid response."""


def request_via_socket(
    socket_path: str,
    payload: dict[str, Any],
    *,
    timeout_sec: float,
) -> dict[str, Any]:
    """Send one newline-delimited JSON request to a Unix socket."""
    path = Path(socket_path).expanduser()
    request_started = False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout_sec)
            try:
                client.connect(str(path))
            except OSError as exc:
                raise IpcUnavailableError(str(exc)) from exc

            try:
                request_started = True
                client.sendall(json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n")
                raw = _readline(client)
            except socket.timeout as exc:
                if request_started:
                    raise IpcRequestTimeoutError(
                        f"Timed out waiting for roamer serve response after {timeout_sec}s"
                    ) from exc
                raise IpcUnavailableError(str(exc)) from exc
            except OSError as exc:
                if request_started:
                    raise IpcProtocolError(str(exc)) from exc
                raise IpcUnavailableError(str(exc)) from exc
    except IpcClientError:
        raise

    if not raw:
        raise IpcProtocolError("Empty response from roamer serve")

    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IpcProtocolError(f"Invalid response from roamer serve: {exc}") from exc

    if not isinstance(decoded, dict):
        raise IpcProtocolError("Invalid response from roamer serve: expected object")
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
        try:
            chunk = sock.recv(1)
        except socket.timeout as exc:
            raise IpcRequestTimeoutError("Timed out reading roamer serve response") from exc
        if not chunk:
            break
        if chunk == b"\n":
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:
            raise IpcProtocolError("Serve request exceeded maximum size")
    return b"".join(chunks)
