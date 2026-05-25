from __future__ import annotations

import asyncio
from pathlib import Path

from roamerd.bridges.control.protocol import RequestEnvelope, ResponseEnvelope


class ControlClient:
    def __init__(self, socket_path: Path) -> None:
        self._socket_path = socket_path

    async def request(self, request: RequestEnvelope) -> ResponseEnvelope:
        reader, writer = await asyncio.open_unix_connection(str(self._socket_path))
        try:
            writer.write(request.model_dump_json(exclude_none=True).encode() + b"\n")
            await writer.drain()
            raw = await reader.readline()
            return ResponseEnvelope.model_validate_json(raw)
        finally:
            writer.close()
            await writer.wait_closed()
