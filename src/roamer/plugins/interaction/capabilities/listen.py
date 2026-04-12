"""Listen capability - voice input and speech recognition."""

import os
import tempfile
import wave
from pathlib import Path
from typing import Any

import numpy as np

# Import drivers to register them
import roamer.plugins.interaction.drivers.speech  # noqa: F401
from roamer.platform.config import get_driver_config, get_driver_name
from roamer.platform.contract import ErrorCode
from roamer.platform.output import error, success
from roamer.plugins.interaction.capabilities.audio import AudioCapability
from roamer.plugins.interaction.capabilities.base import Capability
from roamer.plugins.interaction.drivers.registry import get_driver


class ListenCapability(Capability):
    """Listen capability - voice input with VAD and ASR."""

    def __init__(self, config: dict[str, Any]):
        """Initialize listen capability.

        Args:
            config: Full configuration dictionary
        """
        super().__init__(config)

        # Load VAD driver
        vad_name = get_driver_name(config, "vad")
        vad_config = get_driver_config(config, vad_name)
        self._vad = get_driver("vad", vad_name, vad_config)

        # Load ASR driver
        asr_name = get_driver_name(config, "asr")
        asr_config = get_driver_config(config, asr_name)
        self._asr = get_driver("asr", asr_name, asr_config)

        # Audio capability for recording
        self._audio = AudioCapability(config)

    def _create_temp_audio(self, prefix: str = "roamer_") -> str:
        """Create a secure temporary audio file.

        Args:
            prefix: Filename prefix

        Returns:
            Path to temporary file
        """
        fd, path = tempfile.mkstemp(suffix=".wav", prefix=prefix)
        os.close(fd)
        os.chmod(path, 0o600)
        return path

    def listen(
        self,
        timeout: float = 10.0,
        save_audio: str | None = None,
        debug: bool = False,
    ) -> dict[str, Any]:
        """Listen and transcribe speech.

        Args:
            timeout: Maximum recording duration in seconds
            save_audio: Optional path to save recorded audio
            debug: Enable debug logging to stderr

        Returns:
            Result dict with text, confidence, duration_sec
        """
        import sys

        def log(msg: str) -> None:
            if debug:
                print(f"[listen] {msg}", file=sys.stderr)

        audio_path = save_audio if save_audio else self._create_temp_audio("roamer_rec_")
        trimmed_path = self._create_temp_audio("roamer_speech_")
        cleanup_audio = save_audio is None

        try:
            # Record audio
            log(f"Recording for {timeout}s to {audio_path}")
            record_result = self._audio.record(duration=timeout, output=audio_path)
            if not record_result.get("ok"):
                log(f"Recording failed: {record_result}")
                return record_result

            log(f"Recording complete: {record_result}")

            # Load audio for VAD
            try:
                audio, sample_rate = self._load_wav(audio_path)
                log(f"Loaded audio: shape={audio.shape}, sr={sample_rate}, "
                    f"dtype={audio.dtype}")
                log(f"Audio stats: min={audio.min():.4f}, max={audio.max():.4f}, "
                    f"mean={audio.mean():.4f}, rms={np.sqrt((audio**2).mean()):.4f}")
            except Exception as e:
                log(f"Failed to load audio: {e}")
                return error(
                    "audio_load_failed",
                    f"Failed to load audio: {e}",
                    error_code=ErrorCode.AUDIO_LOAD_FAILED,
                )

            # Run VAD
            log("Running VAD...")
            vad_result = self._vad.detect(audio, sample_rate, debug=debug)
            log(f"VAD result: {vad_result}")
            if not vad_result.get("ok"):
                return vad_result

            if not vad_result.get("speech_detected"):
                log("No speech detected by VAD")
                return error(
                    "vad_no_speech",
                    "No speech detected in recording",
                    error_code=ErrorCode.SPEECH_VAD_NO_SPEECH,
                )

            # Get speech segments
            segments = vad_result.get("segments", [])
            if not segments:
                log("No speech segments found")
                return error(
                    "vad_no_speech",
                    "No speech segments found",
                    error_code=ErrorCode.SPEECH_VAD_NO_SPEECH,
                )

            # Extract speech portion
            start_time = segments[0]["start"]
            end_time = segments[-1]["end"]

            start_sample = int(start_time * sample_rate)
            end_sample = int(end_time * sample_rate)
            speech_audio = audio[start_sample:end_sample]

            # Save trimmed audio for ASR
            try:
                self._save_wav(trimmed_path, speech_audio, sample_rate)
            except Exception as e:
                return error(
                    "audio_save_failed",
                    f"Failed to save trimmed audio: {e}",
                    error_code=ErrorCode.AUDIO_SAVE_FAILED,
                )

            # Run ASR
            asr_result = self._asr.transcribe(trimmed_path)
            if not asr_result.get("ok"):
                return asr_result

            return success(
                text=asr_result.get("text", ""),
                confidence=asr_result.get("confidence"),
                duration_sec=end_time - start_time,
                audio_path=audio_path if save_audio else None,
            )
        finally:
            try:
                Path(trimmed_path).unlink(missing_ok=True)
            except Exception:
                pass
            if cleanup_audio:
                try:
                    Path(audio_path).unlink(missing_ok=True)
                except Exception:
                    pass

    def _load_wav(self, path: str) -> tuple[np.ndarray, int]:
        """Load WAV file as numpy array.

        Args:
            path: Path to WAV file

        Returns:
            Tuple of (audio samples, sample rate)
        """
        with wave.open(path, "rb") as wf:
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()

            raw_data = wf.readframes(n_frames)

            if sample_width == 2:
                audio = np.frombuffer(raw_data, dtype=np.int16)
            elif sample_width == 4:
                audio = np.frombuffer(raw_data, dtype=np.int32)
            else:
                audio = np.frombuffer(raw_data, dtype=np.uint8)

            audio = audio.astype(np.float32)
            if sample_width == 2:
                audio /= 32768.0
            elif sample_width == 4:
                audio /= 2147483648.0
            else:
                audio = (audio - 128.0) / 128.0

            if n_channels > 1:
                audio = audio.reshape(-1, n_channels).mean(axis=1)

            return audio, sample_rate

    def _save_wav(self, path: str, audio: np.ndarray, sample_rate: int) -> None:
        """Save numpy array as WAV file.

        Args:
            path: Output path
            audio: Audio samples (float32, -1 to 1)
            sample_rate: Sample rate
        """
        audio_int16 = (audio * 32767).astype(np.int16)

        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_int16.tobytes())
