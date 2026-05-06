"""Tests for vLLM realtime STT provider."""

import json

from roamer.platform.contract import ErrorCode
from roamer.plugins.interaction.drivers.speech.stt.vllm_realtime import (
    VllmRealtimeSTTProvider,
    normalize_qwen_asr_text,
)


class _FakeConnection:
    def __init__(self, responses: list[dict]):
        self.sent: list[dict] = []
        self._responses = [json.dumps(item) for item in responses]
        self.closed = False

    def recv(self, timeout=None):  # noqa: ANN001 - match websocket sync API
        if not self._responses:
            raise TimeoutError("no more events")
        return self._responses.pop(0)

    def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    def close(self) -> None:
        self.closed = True


def test_vllm_provider_sends_validated_event_sequence() -> None:
    conn = _FakeConnection(
        [
            {"type": "session.created", "id": "s1"},
            {"type": "transcription.delta", "delta": "现在"},
            {"type": "transcription.delta", "delta": "几点"},
            {
                "type": "transcription.done",
                "text": "language Chinese<asr_text>现在几点了？",
            },
        ]
    )
    provider = VllmRealtimeSTTProvider(
        {
            "url": "ws://example.test/v1/realtime",
            "model": "qwen3-asr-0.6b",
        },
        connect_factory=lambda _url, **_kwargs: conn,
        clock=lambda: 0.0,
    )

    provider.start()
    provider.append_pcm16(b"\x01\x02")
    result = provider.finish(timeout_sec=1.0)
    provider.close()

    assert result["ok"] is True
    assert result["text"] == "现在几点了？"
    assert result["provider"] == "vllm_realtime"
    assert conn.sent == [
        {"type": "session.update", "model": "qwen3-asr-0.6b"},
        {"type": "input_audio_buffer.commit"},
        {"type": "input_audio_buffer.append", "audio": "AQI="},
        {"type": "input_audio_buffer.commit", "final": True},
    ]
    assert conn.closed is True


def test_vllm_provider_returns_structured_error_event() -> None:
    conn = _FakeConnection(
        [
            {"type": "session.created", "id": "s1"},
            {"type": "error", "error": "model missing", "code": "model_not_found"},
        ]
    )
    provider = VllmRealtimeSTTProvider(
        {"url": "ws://example.test/v1/realtime", "model": "missing"},
        connect_factory=lambda _url, **_kwargs: conn,
        clock=lambda: 0.0,
    )

    provider.start()
    result = provider.finish(timeout_sec=1.0)

    assert result["ok"] is False
    assert result["error"] == "asr_failed"
    assert result["error_code"] == ErrorCode.SPEECH_ASR_RUNTIME_FAILED
    assert result["provider"] == "vllm_realtime"
    assert result["details"]["vllm_code"] == "model_not_found"


def test_normalize_qwen_asr_text_removes_language_marker() -> None:
    assert normalize_qwen_asr_text("language Chinese<asr_text>瑞彻德现在几点了？") == (
        "瑞彻德现在几点了？"
    )
    assert normalize_qwen_asr_text("<asr_text>现在几点了") == "现在几点了"
    assert normalize_qwen_asr_text("现在几点了") == "现在几点了"
