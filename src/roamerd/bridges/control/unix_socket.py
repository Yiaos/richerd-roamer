"""Newline-delimited JSON Unix socket control server."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from roamerd.bridges.control.bridge import ControlBridge
from roamerd.events.base import JSONDict
from roamerd.events.control import ControlCommandPayload, WaitMode


class UnixSocketControlServer:
    def __init__(self, *, path: str, bridge: ControlBridge) -> None:
        self._path = path
        self._bridge = bridge
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        path = Path(self._path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        self._server = await asyncio.start_unix_server(self._handle, path=self._path)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        line = await reader.readline()
        try:
            request = json.loads(line.decode("utf-8"))
            command = _command_from_wire(request)
            response = await self._bridge.request(command)
        except Exception as exc:
            response = {
                "ok": False,
                "error_code": "control.protocol_error",
                "error_message": str(exc),
            }
        writer.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
        await writer.drain()
        writer.close()
        await writer.wait_closed()


async def request_via_socket(
    path: str, payload: JSONDict, *, timeout_sec: float = 30.0
) -> JSONDict:
    reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(path), timeout=timeout_sec)
    writer.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
    await writer.drain()
    line = await asyncio.wait_for(reader.readline(), timeout=timeout_sec)
    writer.close()
    await writer.wait_closed()
    parsed = json.loads(line.decode("utf-8"))
    return (
        parsed
        if isinstance(parsed, dict)
        else {"ok": False, "error_code": "control.protocol_error"}
    )


def _command_from_wire(payload: object) -> ControlCommandPayload:
    data = payload if isinstance(payload, dict) else {}
    data = _with_timeout_ms(data)
    data = _with_wait_mode(data)
    if "command" in data and "op" not in data:
        command = str(data.get("command"))
        if command in {"ping", "status", "health"}:
            data = {**data, "op": "query", "target": command}
        elif command == "run":
            data = {**data, "op": "run", "args": data.get("params", {})}
        elif command == "converse":
            data = {
                **data,
                "op": "run",
                "action": "listen",
                "args": data.get("args", {}),
                "wait": WaitMode.COMPLETED.value,
            }
        elif command == "action.status":
            data = {
                **data,
                "op": "query",
                "target": "action.status",
                "args": {"action_id": data.get("action_id", "")},
            }
    data.setdefault("correlation_id", uuid4().hex[:12])
    return ControlCommandPayload.model_validate(data)


def _with_timeout_ms(data: dict[object, object]) -> dict[object, object]:
    if "timeout_ms" in data or "timeout_sec" not in data:
        return data
    timeout_sec = data.get("timeout_sec")
    if not isinstance(timeout_sec, (int, float)):
        return data
    return {**data, "timeout_ms": int(timeout_sec * 1000)}


def _with_wait_mode(data: dict[object, object]) -> dict[object, object]:
    if "wait" in data or "wait_mode" not in data:
        return data
    return {**data, "wait": data.get("wait_mode")}
