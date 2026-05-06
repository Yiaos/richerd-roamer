"""Tests for real-time VAD endpointing."""

from pathlib import Path

import numpy as np

from roamer.plugins.interaction.drivers.speech.vad.silero import SileroDriver
from roamer.plugins.interaction.services.endpointing import (
    ChunkVadAdapter,
    EndpointConfig,
    EndpointRecorder,
    pcm_chunk_to_float32,
)


def _chunk(value: int, *, samples: int = 160, channels: int = 1) -> bytes:
    frame = np.full(samples * channels, value, dtype=np.int16)
    return frame.tobytes()


def _record(tmp_path: Path, probs: list[float], chunks: list[bytes] | None = None) -> dict:
    cfg = EndpointConfig(
        silence_sec=0.2,
        min_speech_sec=0.2,
        max_record_sec=2.0,
        pre_speech_padding_sec=0.1,
        no_speech_timeout_sec=0.5,
        threshold=0.5,
        sample_rate=16000,
        channels=1,
        chunk_duration_sec=0.1,
    )
    prob_iter = iter(probs)
    recorder = EndpointRecorder(
        chunk_source=chunks or [_chunk(index + 1) for index in range(len(probs))],
        vad_probability=lambda _audio, _sample_rate: next(prob_iter),
        config=cfg,
        output_path=str(tmp_path / "speech.wav"),
        clock=lambda: 0.0,
    )
    return recorder.record()


def test_pcm_chunk_to_float32_downmixes_channels() -> None:
    stereo = np.array([32767, 32767, -32768, -32768], dtype=np.int16).tobytes()

    audio = pcm_chunk_to_float32(stereo, channels=2)

    assert audio.dtype == np.float32
    assert audio.shape == (2,)
    assert audio[0] > 0.99
    assert audio[1] == -1.0


def test_endpoint_config_clamps_chunks_to_silero_frame_floor() -> None:
    cfg = EndpointConfig.from_config(
        {
            "alsa": {"sample_rate": 16000, "channels": 1},
            "converse": {"endpoint": {"chunk_duration_sec": 0.01}},
        }
    )

    assert cfg.chunk_duration_sec == 0.032


def test_chunk_vad_adapter_uses_native_probability_when_available() -> None:
    class _Vad:
        def probability(self, audio, sample_rate):
            assert sample_rate == 16000
            assert audio.shape == (512,)
            return 0.7

    adapter = ChunkVadAdapter(_Vad(), threshold=0.5)

    assert adapter.probability(np.zeros(512, dtype=np.float32), 16000) == 0.7


def test_chunk_vad_adapter_rejects_undersized_batch_chunks() -> None:
    class _Vad:
        def detect(self, audio, sample_rate, debug=False):  # pragma: no cover - must not call
            raise AssertionError("undersized chunks must not call batch VAD")

    adapter = ChunkVadAdapter(_Vad(), threshold=0.5)

    assert adapter.probability(np.zeros(511, dtype=np.float32), 16000) == 0.0


def test_chunk_vad_adapter_maps_batch_detect_to_probability() -> None:
    class _Vad:
        def detect(self, audio, sample_rate, debug=False):
            assert audio.shape == (512,)
            return {"ok": True, "speech_detected": True}

    adapter = ChunkVadAdapter(_Vad(), threshold=0.5)

    assert adapter.probability(np.zeros(512, dtype=np.float32), 16000) == 1.0


def test_silero_probability_keeps_stream_state_between_chunks() -> None:
    class _Session:
        def __init__(self):
            self.states = []

        def run(self, _outputs, inputs):
            self.states.append(inputs["state"].copy())
            next_state = np.ones((2, 1, 128), dtype=np.float32) * len(self.states)
            return np.array([[0.9]], dtype=np.float32), next_state

    driver = SileroDriver({"model": "/unused"})
    driver._session = _Session()
    driver._sr = np.array(16000, dtype=np.int64)

    first = driver.probability(np.zeros(512, dtype=np.float32), 16000)
    second = driver.probability(np.zeros(512, dtype=np.float32), 16000)

    assert first > 0.89
    assert second > 0.89
    assert np.all(driver._session.states[0] == 0.0)
    assert np.all(driver._session.states[1] == 1.0)


def test_endpoint_resets_streaming_vad_before_each_record(tmp_path: Path) -> None:
    class _Vad:
        def __init__(self):
            self.reset_count = 0

        def reset_stream(self):
            self.reset_count += 1

        def probability(self, _audio, _sample_rate):
            return 0.9

    vad = _Vad()
    cfg = EndpointConfig(
        silence_sec=1.0,
        min_speech_sec=0.1,
        max_record_sec=0.1,
        pre_speech_padding_sec=0.0,
        no_speech_timeout_sec=0.1,
        threshold=0.5,
        sample_rate=16000,
        channels=1,
        chunk_duration_sec=0.1,
    )
    recorder = EndpointRecorder(
        chunk_source=[_chunk(1)],
        vad_probability=ChunkVadAdapter(vad, threshold=0.5).probability,
        config=cfg,
        output_path=str(tmp_path / "speech.wav"),
        clock=lambda: 0.0,
    )

    result = recorder.record()

    assert result["ok"] is True
    assert vad.reset_count == 1


def test_endpoint_no_speech_timeout(tmp_path: Path) -> None:
    result = _record(tmp_path, [0.0, 0.1, 0.2, 0.1, 0.0])

    assert result["ok"] is False
    assert result["error_code"] == "speech.vad.no_speech"
    assert result["endpoint_metrics"]["record_duration_sec"] == 0.5
    assert result["endpoint_metrics"]["speech_duration_sec"] == 0.0


def test_endpoint_short_utterance_preserves_pre_speech_padding(tmp_path: Path) -> None:
    result = _record(tmp_path, [0.0, 0.8, 0.9, 0.1, 0.0])

    assert result["ok"] is True
    assert result["endpoint_metrics"]["record_duration_sec"] == 0.5
    assert result["endpoint_metrics"]["speech_duration_sec"] == 0.2
    assert result["endpoint_metrics"]["endpoint_latency_sec"] == 0.2
    assert Path(result["audio_path"]).exists()
    # 1 pre-speech chunk + 2 speech chunks + 2 trailing silence chunks.
    assert result["size_bytes"] == 44 + (5 * 160 * 2)


def test_endpoint_logs_record_timeline(monkeypatch, tmp_path: Path) -> None:
    events = []
    monkeypatch.setattr(
        "roamer.plugins.interaction.services.endpointing.log_event",
        lambda component, event, **fields: events.append((component, event, fields)),
    )

    result = _record(tmp_path, [0.0, 0.8, 0.9, 0.1, 0.0])

    assert result["ok"] is True
    assert [event for _component, event, _fields in events] == [
        "record_start",
        "speech_start",
        "endpoint_reached",
        "record_done",
    ]
    assert events[0][2]["max_record_sec"] == 2.0
    assert events[1][2]["total_chunks"] == 2
    assert events[2][2]["endpoint_latency_sec"] == 0.2
    assert events[3][2]["ok"] is True


def test_endpoint_logs_record_failure(monkeypatch, tmp_path: Path) -> None:
    events = []
    monkeypatch.setattr(
        "roamer.plugins.interaction.services.endpointing.log_event",
        lambda component, event, **fields: events.append((component, event, fields)),
    )

    result = _record(tmp_path, [0.0, 0.1, 0.2, 0.1, 0.0])

    assert result["ok"] is False
    failed = [item for item in events if item[1] == "record_failed"]
    assert len(failed) == 1
    assert failed[0][2]["reason"] == "no_speech_timeout"
    assert failed[0][2]["endpoint_metrics"]["speech_duration_sec"] == 0.0


def test_endpoint_hesitant_pause_below_silence_does_not_cut(tmp_path: Path) -> None:
    result = _record(tmp_path, [0.0, 0.8, 0.1, 0.9, 0.1, 0.0])

    assert result["ok"] is True
    assert result["endpoint_metrics"]["record_duration_sec"] == 0.6
    assert result["endpoint_metrics"]["speech_duration_sec"] == 0.2
    assert result["endpoint_metrics"]["endpoint_latency_sec"] == 0.2


def test_endpoint_stops_at_max_record_after_speech(tmp_path: Path) -> None:
    cfg = EndpointConfig(
        silence_sec=1.0,
        min_speech_sec=0.1,
        max_record_sec=0.3,
        pre_speech_padding_sec=0.0,
        no_speech_timeout_sec=0.3,
        threshold=0.5,
        sample_rate=16000,
        channels=1,
        chunk_duration_sec=0.1,
    )
    probs = iter([0.9, 0.9, 0.9, 0.9])
    recorder = EndpointRecorder(
        chunk_source=[_chunk(1), _chunk(2), _chunk(3), _chunk(4)],
        vad_probability=lambda _audio, _sample_rate: next(probs),
        config=cfg,
        output_path=str(tmp_path / "max.wav"),
        clock=lambda: 0.0,
    )

    result = recorder.record()

    assert result["ok"] is True
    assert result["endpoint_metrics"]["record_duration_sec"] == 0.3
    assert result["endpoint_metrics"]["speech_duration_sec"] == 0.3
