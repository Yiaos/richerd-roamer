from __future__ import annotations

import wave
from collections import deque
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EndpointConfig:
    chunk_ms: int = 100
    silence_ms: int = 800
    min_duration_ms: int = 300
    max_duration_ms: int = 8000
    pre_padding_ms: int = 200


class EndpointDetector:
    def __init__(self, config: EndpointConfig) -> None:
        self._config = config
        max_pre_roll_chunks = max(config.pre_padding_ms // config.chunk_ms, 0)
        self._pre_roll: deque[bytes] = deque(maxlen=max_pre_roll_chunks)
        self._recording: list[bytes] = []
        self._speech_ms = 0
        self._silence_ms = 0
        self._active = False

    def add_chunk(self, chunk: bytes, *, is_speech: bool) -> bytes | None:
        if not self._active and not is_speech:
            self._pre_roll.append(chunk)
            return None
        if not self._active:
            self._active = True
            self._recording.extend(self._pre_roll)
            self._pre_roll.clear()
        self._recording.append(chunk)
        if is_speech:
            self._speech_ms += self._config.chunk_ms
            self._silence_ms = 0
        else:
            self._silence_ms += self._config.chunk_ms
        total_ms = len(self._recording) * self._config.chunk_ms
        if self._speech_ms >= self._config.min_duration_ms and (
            self._silence_ms >= self._config.silence_ms
            or total_ms >= self._config.max_duration_ms
        ):
            return self._finish()
        return None

    def _finish(self) -> bytes:
        data = b"".join(self._recording)
        self._recording = []
        self._speech_ms = 0
        self._silence_ms = 0
        self._active = False
        return data


def save_wav(path: Path, pcm: bytes, *, sample_rate: int, channels: int) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
