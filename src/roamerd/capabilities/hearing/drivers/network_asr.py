from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from typing import Protocol


class WebSocketSession(Protocol):
    async def __aenter__(self) -> WebSocketSession: ...

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None: ...

    async def send(self, data: bytes) -> None: ...

    async def recv(self) -> str: ...


ConnectFactory = Callable[[str], WebSocketSession]


class NetworkAsrDriver:
    def __init__(
        self,
        url: str,
        *,
        timeout_sec: float = 20.0,
        connect_factory: ConnectFactory | None = None,
    ) -> None:
        self._url = url
        self._timeout_sec = timeout_sec
        self._connect_factory = connect_factory or _default_connect

    async def transcribe(self, pcm: bytes) -> str:
        async with self._connect_factory(self._url) as websocket:
            await websocket.send(pcm)
            text = await asyncio.wait_for(websocket.recv(), timeout=self._timeout_sec)
        return normalize_asr_text(text)


def normalize_asr_text(text: str) -> str:
    return re.sub(r"\s+", "", text).strip()


def _default_connect(url: str) -> WebSocketSession:
    raise RuntimeError(f"websocket client not configured for {url}")
