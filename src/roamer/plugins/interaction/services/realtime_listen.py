"""Endpointed realtime STT listen service."""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import numpy as np

from roamer.platform.contract import ErrorCode
from roamer.platform.output import error
from roamer.plugins.interaction.services.endpointing import EndpointConfig, EndpointRecorder


def pcm_chunk_to_mono_pcm16(chunk: bytes, *, channels: int) -> bytes:
    """Convert S16_LE PCM bytes to mono S16_LE bytes."""
    if not chunk:
        return b""
    audio = np.frombuffer(chunk, dtype=np.int16)
    if channels <= 1:
        return audio.astype(np.int16, copy=False).tobytes()
    audio = audio[: audio.size - (audio.size % channels)]
    if audio.size == 0:
        return b""
    mono = audio.reshape(-1, channels).astype(np.int32).mean(axis=1)
    mono = np.clip(np.rint(mono), -32768, 32767).astype(np.int16)
    return mono.tobytes()


class RealtimeEndpointTranscriber:
    """Run Silero endpointing while streaming finalized utterance chunks to STT."""

    def __init__(
        self,
        *,
        chunk_source: Iterable[bytes],
        vad_probability: Callable[[np.ndarray, int], float],
        endpoint_config: EndpointConfig,
        provider: Any,
        output_path: str | None = None,
        response_timeout_sec: float = 20.0,
        fallback_transcribe: Callable[[str, dict[str, Any] | None], dict[str, Any]] | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self._chunk_source = chunk_source
        self._vad_probability = vad_probability
        self._endpoint_config = endpoint_config
        self._provider = provider
        self._response_timeout_sec = response_timeout_sec
        self._fallback_transcribe = fallback_transcribe
        self._clock = clock
        self._output_path = output_path or self._create_temp_audio()
        self._cleanup_audio = output_path is None

    def transcribe(self) -> dict[str, Any]:
        provider_name = str(
            getattr(self._provider, "config", {}).get("provider") or "vllm_realtime"
        )
        provider_error: Exception | None = None

        def stream_chunk(chunk: bytes) -> None:
            nonlocal provider_error
            if provider_error is not None:
                return
            try:
                self._provider.append_pcm16(
                    pcm_chunk_to_mono_pcm16(chunk, channels=self._endpoint_config.channels)
                )
            except Exception as exc:
                provider_error = exc

        try:
            try:
                self._provider.start()
            except Exception as exc:
                provider_error = exc
            recorder = EndpointRecorder(
                chunk_source=self._chunk_source,
                vad_probability=self._vad_probability,
                config=self._endpoint_config,
                output_path=self._output_path,
                chunk_sink=stream_chunk,
                clock=self._clock,
            )
            try:
                record_result = recorder.record()
            except NotImplementedError as exc:
                return error(
                    "audio_record_failed",
                    str(exc),
                    error_code=ErrorCode.AUDIO_RECORD_COMMAND_FAILED,
                )
            except FileNotFoundError:
                return error(
                    "audio_record_failed",
                    "arecord not installed",
                    error_code=ErrorCode.DEPENDENCY_AUDIO_ARECORD_MISSING,
                )
            except OSError as exc:
                return error(
                    "audio_record_failed",
                    "Endpoint recording failed",
                    details=str(exc),
                    error_code=ErrorCode.AUDIO_RECORD_COMMAND_FAILED,
                )
            if not record_result.get("ok"):
                return record_result

            if provider_error is not None:
                stt_result = error(
                    "asr_failed",
                    "Realtime STT provider failed",
                    details=str(provider_error),
                    error_code=ErrorCode.SPEECH_ASR_RUNTIME_FAILED,
                    provider=provider_name,
                )
            else:
                try:
                    stt_result = self._provider.finish(timeout_sec=self._response_timeout_sec)
                except Exception as exc:
                    stt_result = error(
                        "asr_failed",
                        "Realtime STT provider failed",
                        details=str(exc),
                        error_code=ErrorCode.SPEECH_ASR_RUNTIME_FAILED,
                        provider=provider_name,
                    )
            if stt_result.get("ok"):
                result = dict(stt_result)
                result["endpoint_metrics"] = record_result.get("endpoint_metrics")
                return result

            if self._fallback_transcribe is not None:
                fallback_result = self._fallback_transcribe(
                    self._output_path,
                    record_result.get("endpoint_metrics"),
                )
                if fallback_result.get("ok"):
                    fallback_result = dict(fallback_result)
                    fallback_result["fallback_from"] = provider_name
                    fallback_result.setdefault(
                        "endpoint_metrics", record_result.get("endpoint_metrics")
                    )
                    return fallback_result
            return stt_result
        finally:
            try:
                try:
                    self._provider.close()
                except Exception:
                    pass
            finally:
                if self._cleanup_audio:
                    Path(self._output_path).unlink(missing_ok=True)

    def _create_temp_audio(self) -> str:
        import os

        fd, path = tempfile.mkstemp(suffix=".wav", prefix="roamer_realtime_")
        try:
            os.close(fd)
        finally:
            Path(path).chmod(0o600)
        return path
