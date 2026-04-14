"""Piper TTS driver."""

import subprocess
import wave
from pathlib import Path
from typing import Any

from roamer.platform.contract import ErrorCode
from roamer.platform.output import error, success
from roamer.plugins.interaction.drivers.registry import register_driver
from roamer.plugins.interaction.drivers.speech.tts.base import TTSDriver


class PiperDriver(TTSDriver):
    """TTS driver using Piper."""

    def synthesize(self, text: str, output: str, style: str | None = None) -> dict[str, Any]:
        """Synthesize speech using Piper.

        Args:
            text: Text to synthesize
            output: Output audio file path
            style: Optional emotional expression style

        Returns:
            Result dict
        """
        binary = Path(self.config.get("binary", "~/bin/piper/piper")).expanduser()
        model = Path(self.config.get("model", "")).expanduser()

        if not binary.exists():
            return error(
                "tts_failed",
                f"Piper binary not found: {binary}",
                error_code=ErrorCode.DEPENDENCY_TTS_PIPER_BINARY_MISSING,
            )

        if not model.exists():
            return error(
                "tts_failed",
                f"Piper model not found: {model}",
                error_code=ErrorCode.DEPENDENCY_TTS_PIPER_MODEL_MISSING,
            )

        cmd = [
            str(binary),
            "--model",
            str(model),
            "--output_file",
            output,
        ]

        try:
            result = subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            return error(
                "tts_failed",
                "Synthesis timed out",
                error_code=ErrorCode.SPEECH_TTS_TIMEOUT,
            )
        except FileNotFoundError:
            return error(
                "tts_failed",
                "Piper binary not executable",
                error_code=ErrorCode.DEPENDENCY_TTS_PIPER_BINARY_NOT_EXECUTABLE,
            )

        if result.returncode != 0:
            stderr = result.stderr.decode() if result.stderr else "Unknown error"
            return error(
                "tts_failed",
                stderr,
                error_code=ErrorCode.SPEECH_TTS_SYNTHESIS_FAILED,
            )

        path = Path(output)
        if not path.exists():
            return error(
                "tts_failed",
                "Output file not created",
                error_code=ErrorCode.SPEECH_TTS_OUTPUT_MISSING,
            )

        duration = self._get_wav_duration(output)

        return success(
            path=output,
            text=text,
            duration_sec=duration,
        )

    def _get_wav_duration(self, file: str) -> float | None:
        """Get duration of a WAV file."""
        try:
            with wave.open(file, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                return frames / rate
        except Exception:
            return None


# Register this driver
register_driver("tts", "piper", PiperDriver)
