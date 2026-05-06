"""Real-time VAD endpointing service."""

from __future__ import annotations

import time
import wave
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from roamer.platform.contract import ErrorCode
from roamer.platform.logging import log_event
from roamer.platform.output import error, success


@dataclass(frozen=True)
class EndpointConfig:
    """Runtime settings for chunk-based endpointing."""

    silence_sec: float = 2.0
    min_speech_sec: float = 0.2
    max_record_sec: float = 10.0
    pre_speech_padding_sec: float = 0.3
    no_speech_timeout_sec: float = 10.0
    threshold: float = 0.5
    sample_rate: int = 16000
    channels: int = 2
    sample_width_bytes: int = 2
    chunk_duration_sec: float = 0.032

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> "EndpointConfig":
        endpoint = config.get("converse", {}).get("endpoint", {})
        alsa = config.get("alsa", {})
        silero = config.get("silero", {})
        max_record = float(endpoint.get("max_record_sec", timeout or cls.max_record_sec))
        if timeout is not None:
            max_record = min(max_record, float(timeout))
        # Silero VAD processes 512 samples at 16kHz (32ms). Keep endpoint chunks
        # at or above that floor so the current chunk adapter cannot silently
        # produce no speech forever with undersized chunks.
        chunk_duration_sec = max(
            cls.chunk_duration_sec,
            float(endpoint.get("chunk_duration_sec", cls.chunk_duration_sec)),
        )
        return cls(
            silence_sec=float(endpoint.get("silence_sec", cls.silence_sec)),
            min_speech_sec=float(endpoint.get("min_speech_sec", cls.min_speech_sec)),
            max_record_sec=max_record,
            pre_speech_padding_sec=float(
                endpoint.get("pre_speech_padding_sec", cls.pre_speech_padding_sec)
            ),
            no_speech_timeout_sec=float(endpoint.get("no_speech_timeout_sec", max_record)),
            threshold=float(silero.get("threshold", cls.threshold)),
            sample_rate=int(alsa.get("sample_rate", cls.sample_rate)),
            channels=int(alsa.get("channels", cls.channels)),
            chunk_duration_sec=chunk_duration_sec,
        )


def pcm_chunk_to_float32(chunk: bytes, *, channels: int) -> np.ndarray:
    """Convert S16_LE PCM bytes to mono float32 samples."""
    if not chunk:
        return np.array([], dtype=np.float32)
    audio = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1 and audio.size >= channels:
        audio = audio[: audio.size - (audio.size % channels)]
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio.astype(np.float32, copy=False)


class ChunkVadAdapter:
    """Small adapter that turns an existing VAD driver into chunk probabilities.

    This adapter intentionally supports the existing batch Silero driver without
    pretending it is a full streaming-probability API: if the driver exposes a
    native ``probability`` method, use it; otherwise require at least one Silero
    frame (512 samples at 16kHz) and map batch speech detection to 1.0/0.0.
    """

    _MIN_16K_SAMPLES = 512

    def __init__(self, vad: Any, *, threshold: float):
        self._vad = vad
        self._threshold = threshold

    def probability(self, audio: np.ndarray, sample_rate: int) -> float:
        native_probability = getattr(self._vad, "probability", None)
        if callable(native_probability):
            return float(native_probability(audio, sample_rate))

        if audio.size < self._minimum_samples(sample_rate):
            return 0.0

        result = self._vad.detect(audio, sample_rate, debug=False)
        if not result.get("ok"):
            return 0.0
        if result.get("speech_detected"):
            return max(self._threshold, 1.0)
        return 0.0

    def reset_stream(self) -> None:
        reset = getattr(self._vad, "reset_stream", None)
        if callable(reset):
            reset()

    def _minimum_samples(self, sample_rate: int) -> int:
        if sample_rate == 16000:
            return self._MIN_16K_SAMPLES
        return max(1, int(round(self._MIN_16K_SAMPLES * (sample_rate / 16000))))


class EndpointRecorder:
    """Finalize one utterance from raw audio chunks and VAD probabilities."""

    def __init__(
        self,
        *,
        chunk_source: Iterable[bytes],
        vad_probability: Callable[[np.ndarray, int], float],
        config: EndpointConfig,
        output_path: str,
        chunk_sink: Callable[[bytes], None] | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self._chunk_source = chunk_source
        self._vad_probability = vad_probability
        self._config = config
        self._output_path = output_path
        self._chunk_sink = chunk_sink
        self._clock = clock or time.monotonic

    def record(self) -> dict[str, Any]:
        cfg = self._config
        reset_stream = getattr(self._vad_probability, "__self__", None)
        if reset_stream is not None:
            reset = getattr(reset_stream, "reset_stream", None)
            if callable(reset):
                reset()
        pre_chunks = max(0, int(round(cfg.pre_speech_padding_sec / cfg.chunk_duration_sec)))
        silence_chunks = max(1, int(round(cfg.silence_sec / cfg.chunk_duration_sec)))
        min_speech_chunks = max(1, int(round(cfg.min_speech_sec / cfg.chunk_duration_sec)))
        max_chunks = max(1, int(round(cfg.max_record_sec / cfg.chunk_duration_sec)))
        no_speech_chunks = max(1, int(round(cfg.no_speech_timeout_sec / cfg.chunk_duration_sec)))

        prefix: deque[bytes] = deque(maxlen=pre_chunks)
        recorded: list[bytes] = []
        speech_started = False
        speech_chunks = 0
        total_chunks = 0
        silence_after_speech = 0
        endpoint_latency_sec: float | None = None
        start_time = self._clock()
        log_event(
            "endpoint",
            "record_start",
            max_record_sec=cfg.max_record_sec,
            silence_sec=cfg.silence_sec,
            min_speech_sec=cfg.min_speech_sec,
            no_speech_timeout_sec=cfg.no_speech_timeout_sec,
            chunk_duration_sec=cfg.chunk_duration_sec,
            threshold=cfg.threshold,
        )

        for raw_chunk in self._chunk_source:
            if not raw_chunk:
                continue
            total_chunks += 1
            audio = pcm_chunk_to_float32(raw_chunk, channels=cfg.channels)
            prob = float(self._vad_probability(audio, cfg.sample_rate))
            is_speech = prob >= cfg.threshold

            if not speech_started:
                if is_speech:
                    speech_started = True
                    recorded.extend(prefix)
                    for prefix_chunk in prefix:
                        self._emit_chunk(prefix_chunk)
                    recorded.append(raw_chunk)
                    self._emit_chunk(raw_chunk)
                    speech_chunks += 1
                    silence_after_speech = 0
                    log_event(
                        "endpoint",
                        "speech_start",
                        total_chunks=total_chunks,
                        speech_chunks=speech_chunks,
                        probability=round(prob, 6),
                        record_duration_sec=round(total_chunks * cfg.chunk_duration_sec, 6),
                    )
                else:
                    prefix.append(raw_chunk)
                    if total_chunks >= no_speech_chunks:
                        metrics = self._metrics(
                            total_chunks=total_chunks,
                            speech_chunks=0,
                            endpoint_latency_sec=None,
                            wall_duration_sec=self._clock() - start_time,
                        )
                        log_event(
                            "endpoint",
                            "record_failed",
                            ok=False,
                            reason="no_speech_timeout",
                            error_code=ErrorCode.SPEECH_VAD_NO_SPEECH,
                            total_chunks=total_chunks,
                            speech_chunks=0,
                            endpoint_metrics=metrics,
                            **metrics,
                        )
                        return error(
                            "vad_no_speech",
                            "No speech detected before endpoint timeout",
                            error_code=ErrorCode.SPEECH_VAD_NO_SPEECH,
                            endpoint_metrics=metrics,
                        )
            else:
                recorded.append(raw_chunk)
                self._emit_chunk(raw_chunk)
                if is_speech:
                    speech_chunks += 1
                    silence_after_speech = 0
                else:
                    silence_after_speech += 1

                if (
                    speech_chunks >= min_speech_chunks
                    and silence_after_speech >= silence_chunks
                ):
                    endpoint_latency_sec = silence_after_speech * cfg.chunk_duration_sec
                    log_event(
                        "endpoint",
                        "endpoint_reached",
                        total_chunks=total_chunks,
                        speech_chunks=speech_chunks,
                        silence_after_speech=silence_after_speech,
                        endpoint_latency_sec=round(endpoint_latency_sec, 6),
                        record_duration_sec=round(total_chunks * cfg.chunk_duration_sec, 6),
                    )
                    break

            if total_chunks >= max_chunks:
                endpoint_latency_sec = 0.0 if speech_started else None
                break

        if not speech_started:
            metrics = self._metrics(
                total_chunks=total_chunks,
                speech_chunks=0,
                endpoint_latency_sec=None,
                wall_duration_sec=self._clock() - start_time,
            )
            log_event(
                "endpoint",
                "record_failed",
                ok=False,
                reason="stream_ended_no_speech",
                error_code=ErrorCode.SPEECH_VAD_NO_SPEECH,
                total_chunks=total_chunks,
                speech_chunks=0,
                endpoint_metrics=metrics,
                **metrics,
            )
            return error(
                "vad_no_speech",
                "No speech detected before audio stream ended",
                error_code=ErrorCode.SPEECH_VAD_NO_SPEECH,
                endpoint_metrics=metrics,
            )

        self._save_wav(recorded)
        path = Path(self._output_path)
        metrics = self._metrics(
            total_chunks=total_chunks,
            speech_chunks=speech_chunks,
            endpoint_latency_sec=endpoint_latency_sec,
            wall_duration_sec=self._clock() - start_time,
        )
        log_event(
            "endpoint",
            "record_done",
            ok=True,
            total_chunks=total_chunks,
            speech_chunks=speech_chunks,
            endpoint_metrics=metrics,
            **metrics,
        )
        return success(
            path=self._output_path,
            audio_path=self._output_path,
            sample_rate=cfg.sample_rate,
            channels=cfg.channels,
            size_bytes=path.stat().st_size,
            endpoint_metrics=metrics,
            **metrics,
        )

    def _metrics(
        self,
        *,
        total_chunks: int,
        speech_chunks: int,
        endpoint_latency_sec: float | None,
        wall_duration_sec: float,
    ) -> dict[str, Any]:
        cfg = self._config
        metrics: dict[str, Any] = {
            "record_duration_sec": round(total_chunks * cfg.chunk_duration_sec, 6),
            "speech_duration_sec": round(speech_chunks * cfg.chunk_duration_sec, 6),
            "wall_duration_sec": round(wall_duration_sec, 6),
        }
        if endpoint_latency_sec is not None:
            metrics["endpoint_latency_sec"] = round(endpoint_latency_sec, 6)
        return metrics

    def _save_wav(self, chunks: list[bytes]) -> None:
        Path(self._output_path).parent.mkdir(parents=True, exist_ok=True)
        with wave.open(self._output_path, "wb") as wf:
            wf.setnchannels(int(self._config.channels))
            wf.setsampwidth(int(self._config.sample_width_bytes))
            wf.setframerate(int(self._config.sample_rate))
            wf.writeframes(b"".join(chunks))

    def _emit_chunk(self, chunk: bytes) -> None:
        if self._chunk_sink is not None:
            self._chunk_sink(chunk)
