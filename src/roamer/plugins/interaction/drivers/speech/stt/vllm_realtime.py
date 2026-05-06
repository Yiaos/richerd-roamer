"""vLLM realtime ASR provider for Qwen3-ASR."""

from __future__ import annotations

import base64
import json
import re
import time
from collections.abc import Callable
from typing import Any

from roamer.platform.contract import ErrorCode
from roamer.platform.output import error, success
from roamer.plugins.interaction.drivers.speech.stt.base import RealtimeSTTProvider


def normalize_qwen_asr_text(text: str) -> str:
    """Remove Qwen ASR prompt markers from a transcript."""
    normalized = str(text or "").strip()
    if "<asr_text>" in normalized:
        normalized = normalized.split("<asr_text>", 1)[1]
    normalized = re.sub(r"^language\s+[A-Za-z_-]+\s*", "", normalized).strip()
    return normalized


class VllmRealtimeSTTProvider(RealtimeSTTProvider):
    """Synchronous client for vLLM's realtime ASR WebSocket protocol."""

    def __init__(
        self,
        config: dict[str, Any],
        *,
        connect_factory: Callable[..., Any] | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self.config = config
        self.url = str(config.get("url") or "")
        self.model = str(config.get("model") or "qwen3-asr-0.6b")
        self.connect_timeout_sec = float(config.get("connect_timeout_sec", 5.0))
        self._connect_factory = connect_factory
        self._clock = clock or time.monotonic
        self._ws: Any | None = None
        self._started_at: float | None = None
        self._done = False

    def start(self) -> None:
        if not self.url:
            raise RuntimeError("vLLM realtime STT url is required")
        if self._ws is not None:
            return

        connect_factory = self._connect_factory or self._load_default_connect_factory()
        self._ws = self._connect(connect_factory)
        self._started_at = self._clock()
        self._consume_initial_event()
        self._send({"type": "session.update", "model": self.model})
        # vLLM uses this first commit to start the ASR stream.
        self._send({"type": "input_audio_buffer.commit"})

    def append_pcm16(self, chunk: bytes) -> None:
        if not chunk:
            return
        self._ensure_started()
        self._send(
            {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(chunk).decode("ascii"),
            }
        )

    def finish(self, timeout_sec: float) -> dict[str, Any]:
        self._ensure_started()
        if not self._done:
            self._send({"type": "input_audio_buffer.commit", "final": True})
            self._done = True

        deadline = self._clock() + float(timeout_sec)
        deltas: list[str] = []

        while True:
            remaining = max(0.0, deadline - self._clock())
            if remaining <= 0:
                return error(
                    "asr_failed",
                    "Realtime STT timed out waiting for transcription.done",
                    error_code=ErrorCode.SPEECH_ASR_RUNTIME_FAILED,
                    provider="vllm_realtime",
                )

            try:
                event = self._recv(timeout=remaining)
            except TimeoutError:
                return error(
                    "asr_failed",
                    "Realtime STT timed out waiting for transcription.done",
                    error_code=ErrorCode.SPEECH_ASR_RUNTIME_FAILED,
                    provider="vllm_realtime",
                )
            except Exception as exc:
                return error(
                    "asr_failed",
                    "Realtime STT receive failed",
                    details=str(exc),
                    error_code=ErrorCode.SPEECH_ASR_RUNTIME_FAILED,
                    provider="vllm_realtime",
                )

            event_type = event.get("type")
            if event_type == "transcription.delta":
                deltas.append(str(event.get("delta") or ""))
                continue
            if event_type == "transcription.done":
                text = str(event.get("text") or "".join(deltas))
                return success(
                    text=normalize_qwen_asr_text(text),
                    provider="vllm_realtime",
                    duration_sec=self._duration_sec(),
                    usage=event.get("usage"),
                )
            if event_type == "error":
                return error(
                    "asr_failed",
                    str(event.get("error") or "Realtime STT provider returned an error"),
                    error_code=ErrorCode.SPEECH_ASR_RUNTIME_FAILED,
                    provider="vllm_realtime",
                    details={"vllm_code": event.get("code"), "event": event},
                )

    def close(self) -> None:
        ws = self._ws
        self._ws = None
        if ws is None:
            return
        close = getattr(ws, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass

    def _load_default_connect_factory(self) -> Callable[..., Any]:
        try:
            from websockets.sync.client import connect
        except ImportError as exc:
            raise RuntimeError(
                "websockets is required for vLLM realtime STT; install roamer[speech]"
            ) from exc
        return connect

    def _connect(self, connect_factory: Callable[..., Any]) -> Any:
        try:
            return connect_factory(
                self.url,
                open_timeout=self.connect_timeout_sec,
                proxy=None,
            )
        except TypeError:
            return connect_factory(self.url, open_timeout=self.connect_timeout_sec)

    def _consume_initial_event(self) -> None:
        try:
            event = self._recv(timeout=self.connect_timeout_sec)
        except TimeoutError:
            return
        if event.get("type") == "error":
            raise RuntimeError(str(event.get("error") or "vLLM realtime session error"))

    def _send(self, event: dict[str, Any]) -> None:
        self._ensure_started()
        self._ws.send(json.dumps(event, ensure_ascii=False))

    def _recv(self, *, timeout: float) -> dict[str, Any]:
        self._ensure_started()
        raw = self._ws.recv(timeout=timeout)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        parsed = json.loads(str(raw))
        if not isinstance(parsed, dict):
            raise ValueError("vLLM realtime event must be a JSON object")
        return parsed

    def _ensure_started(self) -> None:
        if self._ws is None:
            raise RuntimeError("vLLM realtime STT provider is not started")

    def _duration_sec(self) -> float:
        if self._started_at is None:
            return 0.0
        return round(max(0.0, self._clock() - self._started_at), 6)
