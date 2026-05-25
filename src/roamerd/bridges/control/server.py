from __future__ import annotations

import asyncio
import os
from pathlib import Path

from roamerd.bridges.control.commands import Router
from roamerd.bridges.control.protocol import (
    ProtocolError,
    ResponseEnvelope,
    decode_request_line,
    encode_response,
)
from roamerd.kernel.event_bus import EventBus


class ControlBridgeServer:
    name = "control"

    def __init__(self, *, socket_path: Path, router: Router) -> None:
        self._socket_path = socket_path
        self._router = router
        self._server: asyncio.AbstractServer | None = None

    async def start(self, bus: EventBus | None = None) -> None:
        if self._socket_path.exists():
            if await self._socket_is_active():
                raise RuntimeError(f"active control socket already exists: {self._socket_path}")
            self._socket_path.unlink()
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self._socket_path),
        )
        os.chmod(self._socket_path, 0o600)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def health_check(self) -> str:
        return "healthy"

    async def _socket_is_active(self) -> bool:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(str(self._socket_path)),
                timeout=0.5,
            )
        except (OSError, TimeoutError):
            return False
        writer.close()
        await writer.wait_closed()
        return True

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            raw = await reader.readline()
            try:
                request = decode_request_line(raw)
                response = await self._router.dispatch(request)
            except ProtocolError as exc:
                response = ResponseEnvelope(
                    request_id="",
                    status="error",
                    op="unknown",
                    error={"code": "PROTOCOL_ERROR", "message": str(exc)},
                )
            writer.write(encode_response(response))
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
