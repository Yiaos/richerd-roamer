"""Tests for endpointed realtime STT listen service."""

from pathlib import Path
from unittest.mock import Mock

import numpy as np

from roamer.plugins.interaction.services.endpointing import EndpointConfig
from roamer.plugins.interaction.services.realtime_listen import (
    RealtimeEndpointTranscriber,
    pcm_chunk_to_mono_pcm16,
)


def _chunk(values: list[int], *, channels: int = 2) -> bytes:
    return np.array(values, dtype=np.int16).reshape(-1, channels).tobytes()


class _FakeProvider:
    def __init__(self, result: dict):
        self.result = result
        self.started = False
        self.closed = False
        self.chunks: list[bytes] = []
        self.finish_timeout = None

    def start(self) -> None:
        self.started = True

    def append_pcm16(self, chunk: bytes) -> None:
        self.chunks.append(chunk)

    def finish(self, timeout_sec: float) -> dict:
        self.finish_timeout = timeout_sec
        return self.result

    def close(self) -> None:
        self.closed = True


def _cfg() -> EndpointConfig:
    return EndpointConfig(
        silence_sec=0.2,
        min_speech_sec=0.1,
        max_record_sec=2.0,
        pre_speech_padding_sec=0.1,
        no_speech_timeout_sec=0.5,
        threshold=0.5,
        sample_rate=16000,
        channels=2,
        chunk_duration_sec=0.1,
    )


def test_pcm_chunk_to_mono_pcm16_downmixes_stereo() -> None:
    chunk = _chunk([1000, 3000, -1000, -3000])

    assert np.frombuffer(pcm_chunk_to_mono_pcm16(chunk, channels=2), dtype=np.int16).tolist() == [
        2000,
        -2000,
    ]


def test_realtime_endpoint_transcriber_streams_endpointed_chunks(tmp_path: Path) -> None:
    provider = _FakeProvider({"ok": True, "text": "现在几点了", "provider": "vllm_realtime"})
    probs = iter([0.0, 0.9, 0.8, 0.1, 0.0])
    transcriber = RealtimeEndpointTranscriber(
        chunk_source=[
            _chunk([1, 1]),
            _chunk([2, 2]),
            _chunk([3, 3]),
            _chunk([4, 4]),
            _chunk([5, 5]),
        ],
        vad_probability=lambda _audio, _sample_rate: next(probs),
        endpoint_config=_cfg(),
        provider=provider,
        output_path=str(tmp_path / "utterance.wav"),
        response_timeout_sec=7.0,
        clock=lambda: 0.0,
    )

    result = transcriber.transcribe()

    assert result["ok"] is True
    assert result["text"] == "现在几点了"
    assert result["provider"] == "vllm_realtime"
    assert result["endpoint_metrics"]["record_duration_sec"] == 0.5
    assert provider.started is True
    assert provider.finish_timeout == 7.0
    assert provider.closed is True
    # 1 pre-speech chunk + 2 speech chunks + 2 trailing silence chunks.
    assert [np.frombuffer(chunk, dtype=np.int16).tolist() for chunk in provider.chunks] == [
        [1],
        [2],
        [3],
        [4],
        [5],
    ]


def test_realtime_endpoint_transcriber_falls_back_to_batch(tmp_path: Path) -> None:
    provider = _FakeProvider({"ok": False, "error": "asr_failed", "provider": "vllm_realtime"})
    probs = iter([0.9, 0.1, 0.0])
    fallback_paths = []

    def _fallback(path: str, endpoint_metrics: dict | None) -> dict:
        fallback_paths.append((path, endpoint_metrics))
        return {"ok": True, "text": "fallback", "provider": "funasr"}

    transcriber = RealtimeEndpointTranscriber(
        chunk_source=[_chunk([1, 1]), _chunk([2, 2]), _chunk([3, 3])],
        vad_probability=lambda _audio, _sample_rate: next(probs),
        endpoint_config=_cfg(),
        provider=provider,
        output_path=str(tmp_path / "utterance.wav"),
        response_timeout_sec=7.0,
        fallback_transcribe=_fallback,
        clock=lambda: 0.0,
    )

    result = transcriber.transcribe()

    assert result["ok"] is True
    assert result["text"] == "fallback"
    assert result["provider"] == "funasr"
    assert result["fallback_from"] == "vllm_realtime"
    assert len(fallback_paths) == 1
    assert Path(fallback_paths[0][0]).exists()


def test_realtime_endpoint_transcriber_suppresses_provider_close_error(
    tmp_path: Path,
) -> None:
    provider = _FakeProvider({"ok": True, "text": "现在几点了", "provider": "vllm_realtime"})
    provider.close = Mock(side_effect=RuntimeError("close failed"))
    probs = iter([0.9, 0.1, 0.0])
    transcriber = RealtimeEndpointTranscriber(
        chunk_source=[_chunk([1, 1]), _chunk([2, 2]), _chunk([3, 3])],
        vad_probability=lambda _audio, _sample_rate: next(probs),
        endpoint_config=_cfg(),
        provider=provider,
        output_path=str(tmp_path / "utterance.wav"),
        response_timeout_sec=7.0,
        clock=lambda: 0.0,
    )

    result = transcriber.transcribe()

    assert result["ok"] is True
    assert result["text"] == "现在几点了"


def test_realtime_endpoint_transcriber_returns_structured_audio_error(
    tmp_path: Path,
) -> None:
    provider = _FakeProvider({"ok": True, "text": "unused"})

    def _chunks():
        raise FileNotFoundError("arecord")
        yield b""  # pragma: no cover

    transcriber = RealtimeEndpointTranscriber(
        chunk_source=_chunks(),
        vad_probability=lambda _audio, _sample_rate: 0.0,
        endpoint_config=_cfg(),
        provider=provider,
        output_path=str(tmp_path / "utterance.wav"),
        response_timeout_sec=7.0,
        clock=lambda: 0.0,
    )

    result = transcriber.transcribe()

    assert result["ok"] is False
    assert result["error"] == "audio_record_failed"
    assert result["error_code"] == "dependency.audio.arecord_missing"


def test_realtime_endpoint_transcriber_records_and_falls_back_after_provider_start_error(
    tmp_path: Path,
) -> None:
    provider = _FakeProvider({"ok": True, "text": "unused"})
    provider.start = Mock(side_effect=RuntimeError("connect failed"))
    probs = iter([0.9, 0.1, 0.0])
    fallback_paths = []

    def _fallback(path: str, endpoint_metrics: dict | None) -> dict:
        fallback_paths.append((path, endpoint_metrics))
        return {"ok": True, "text": "fallback", "provider": "funasr"}

    transcriber = RealtimeEndpointTranscriber(
        chunk_source=[_chunk([1, 1]), _chunk([2, 2]), _chunk([3, 3])],
        vad_probability=lambda _audio, _sample_rate: next(probs),
        endpoint_config=_cfg(),
        provider=provider,
        output_path=str(tmp_path / "utterance.wav"),
        response_timeout_sec=7.0,
        fallback_transcribe=_fallback,
        clock=lambda: 0.0,
    )

    result = transcriber.transcribe()

    assert result["ok"] is True
    assert result["provider"] == "funasr"
    assert result["fallback_from"] == "vllm_realtime"
    assert provider.chunks == []
    assert len(fallback_paths) == 1
