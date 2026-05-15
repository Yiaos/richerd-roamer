"""Network ASR driver for vLLM/Qwen realtime websocket transcription."""

from __future__ import annotations

import asyncio
import base64
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from roamerd.events.hearing import TranscriptPayload
from roamerd.kernel.state_manager import HealthState


@runtime_checkable
class SttLike(Protocol):
    async def transcribe(
        self, audio_path: str | None = None, *, timeout: float = 10.0
    ) -> TranscriptPayload: ...

    async def health_check(self) -> HealthState: ...


class NetworkAsrDriver:
    def __init__(
        self,
        *,
        url: str,
        model: str,
        connect_timeout_sec: float = 5.0,
        chunk_size: int = 32 * 1024,
        connect_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._url = url
        self._model = model
        self._connect_timeout_sec = connect_timeout_sec
        self._chunk_size = chunk_size
        self._connect_factory = connect_factory

    async def transcribe(
        self, audio_path: str | None = None, *, timeout: float = 10.0
    ) -> TranscriptPayload:
        if audio_path is None:
            raise RuntimeError("audio_path is required for network ASR")
        path = Path(audio_path)
        if not path.exists():
            raise RuntimeError(f"audio file not found: {audio_path}")
        result = await asyncio.to_thread(self._transcribe_sync, path, timeout)
        return TranscriptPayload(text=result, audio_path=str(path))

    async def health_check(self) -> HealthState:
        return HealthState.HEALTHY if self._url else HealthState.DEGRADED

    def _transcribe_sync(self, path: Path, timeout: float) -> str:
        if not self._url:
            raise RuntimeError("network ASR url is required")
        connect_factory = self._connect_factory or _load_default_connect_factory()
        try:
            websocket = connect_factory(
                self._url,
                open_timeout=self._connect_timeout_sec,
                proxy=None,
            )
        except TypeError:
            websocket = connect_factory(self._url, open_timeout=self._connect_timeout_sec)
        try:
            _consume_initial_event(websocket, self._connect_timeout_sec)
            websocket.send(json.dumps({"type": "session.update", "model": self._model}))
            with open(path, "rb") as handle:
                for chunk in iter(lambda: handle.read(self._chunk_size), b""):
                    websocket.send(
                        json.dumps(
                            {
                                "type": "input_audio_buffer.append",
                                "audio": base64.b64encode(chunk).decode("ascii"),
                            }
                        )
                    )
            websocket.send(json.dumps({"type": "input_audio_buffer.commit", "final": True}))
            return _receive_transcript(websocket, timeout)
        finally:
            close = getattr(websocket, "close", None)
            if callable(close):
                close()


class NetworkThenBatchSttDriver:
    def __init__(self, *, primary: SttLike, fallback: SttLike) -> None:
        self._primary = primary
        self._fallback = fallback

    async def transcribe(
        self, audio_path: str | None = None, *, timeout: float = 10.0
    ) -> TranscriptPayload:
        try:
            return await self._primary.transcribe(audio_path, timeout=timeout)
        except Exception:
            return await self._fallback.transcribe(audio_path, timeout=timeout)

    async def health_check(self) -> HealthState:
        primary_health = await self._primary.health_check()
        if primary_health == HealthState.HEALTHY:
            return HealthState.HEALTHY
        fallback_health = await self._fallback.health_check()
        return (
            HealthState.DEGRADED
            if fallback_health == HealthState.HEALTHY
            else HealthState.UNAVAILABLE
        )


def normalize_qwen_asr_text(text: str) -> str:
    normalized = str(text or "").strip()
    if "<asr_text>" in normalized:
        normalized = normalized.split("<asr_text>", 1)[1]
    return re.sub(r"^language\s+[A-Za-z_-]+\s*", "", normalized).strip()


def _receive_transcript(websocket: Any, timeout: float) -> str:
    deltas: list[str] = []
    while True:
        event = _recv_event(websocket, timeout)
        event_type = event.get("type")
        if event_type == "transcription.delta":
            deltas.append(str(event.get("delta") or ""))
        elif event_type == "transcription.done":
            return normalize_qwen_asr_text(str(event.get("text") or "".join(deltas)))
        elif event_type == "error":
            raise RuntimeError(str(event.get("error") or "network ASR error"))


def _consume_initial_event(websocket: Any, timeout: float) -> None:
    try:
        event = _recv_event(websocket, timeout)
    except TimeoutError:
        return
    if event.get("type") == "error":
        raise RuntimeError(str(event.get("error") or "network ASR session error"))


def _recv_event(websocket: Any, timeout: float) -> dict[str, Any]:
    raw = websocket.recv(timeout=timeout)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    parsed = json.loads(str(raw))
    if not isinstance(parsed, dict):
        raise RuntimeError("network ASR event must be a JSON object")
    return parsed


def _load_default_connect_factory() -> Callable[..., Any]:
    try:
        from websockets.sync.client import connect
    except ImportError as exc:
        raise RuntimeError("websockets is required for network ASR") from exc
    return connect
