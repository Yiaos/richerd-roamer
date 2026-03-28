"""Silero VAD driver."""

from pathlib import Path
from typing import Any

import numpy as np

from roamer.drivers.registry import register_driver
from roamer.drivers.speech.vad.base import VADDriver
from roamer.output import error, success


class SileroDriver(VADDriver):
    """VAD driver using silero-vad ONNX model."""

    def __init__(self, config: dict[str, Any]):
        """Initialize silero VAD driver.

        Args:
            config: Driver-specific configuration
        """
        super().__init__(config)
        self._session = None
        self._state = None
        self._sr = None

    def _load_model(self) -> bool:
        """Load the ONNX model if not already loaded.

        Returns:
            True if model loaded successfully
        """
        if self._session is not None:
            return True

        try:
            import onnxruntime as ort
        except ImportError:
            return False

        model_path = Path(self.config.get("model", "")).expanduser()
        if not model_path.exists():
            return False

        try:
            self._session = ort.InferenceSession(
                str(model_path),
                providers=["CPUExecutionProvider"],
            )
            # Initialize state for silero-vad
            self._state = np.zeros((2, 1, 128), dtype=np.float32)
            self._sr = np.array([16000], dtype=np.int64)
            return True
        except Exception:
            return False

    def detect(self, audio: np.ndarray, sample_rate: int) -> dict[str, Any]:
        """Detect speech segments in audio.

        Args:
            audio: Audio samples as numpy array (mono, float32, -1 to 1)
            sample_rate: Sample rate in Hz

        Returns:
            Result dict with speech_detected, segments
        """
        if not self._load_model():
            return error("vad_failed", "Failed to load VAD model")

        threshold = self.config.get("threshold", 0.5)

        # Ensure mono audio
        if len(audio.shape) > 1:
            audio = audio.mean(axis=1)

        # Ensure float32
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Normalize if needed
        max_val = np.abs(audio).max()
        if max_val > 1.0:
            audio = audio / max_val

        # Resample to 16kHz if needed
        if sample_rate != 16000:
            # Simple decimation/interpolation
            ratio = 16000 / sample_rate
            new_length = int(len(audio) * ratio)
            indices = np.linspace(0, len(audio) - 1, new_length)
            audio = np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)

        # Process in 512-sample chunks (32ms at 16kHz)
        chunk_size = 512
        segments: list[dict[str, float]] = []
        speech_frames: list[int] = []

        # Reset state for new audio
        self._state = np.zeros((2, 1, 128), dtype=np.float32)

        for i in range(0, len(audio) - chunk_size + 1, chunk_size):
            chunk = audio[i : i + chunk_size].reshape(1, -1)

            try:
                ort_inputs = {
                    "input": chunk,
                    "state": self._state,
                    "sr": self._sr,
                }
                output, self._state = self._session.run(None, ort_inputs)
                prob = output[0][0]

                if prob > threshold:
                    speech_frames.append(i)
            except Exception:
                continue

        # Convert frames to segments
        if speech_frames:
            segments = self._frames_to_segments(speech_frames, chunk_size, 16000)

        speech_detected = len(segments) > 0

        if not speech_detected:
            return success(
                speech_detected=False,
                segments=[],
            )

        return success(
            speech_detected=True,
            segments=segments,
        )

    def _frames_to_segments(
        self, frames: list[int], chunk_size: int, sample_rate: int
    ) -> list[dict[str, float]]:
        """Convert frame indices to time segments.

        Args:
            frames: List of frame start indices with speech
            chunk_size: Size of each chunk in samples
            sample_rate: Sample rate

        Returns:
            List of segment dicts with start/end times
        """
        if not frames:
            return []

        segments = []
        start = frames[0]
        prev = frames[0]

        # Merge frames within 300ms of each other
        merge_samples = int(0.3 * sample_rate)

        for frame in frames[1:]:
            if frame - prev > merge_samples:
                # Gap too large, end current segment
                segments.append({
                    "start": start / sample_rate,
                    "end": (prev + chunk_size) / sample_rate,
                })
                start = frame
            prev = frame

        # Add final segment
        segments.append({
            "start": start / sample_rate,
            "end": (prev + chunk_size) / sample_rate,
        })

        return segments


# Register this driver
register_driver("vad", "silero", SileroDriver)
