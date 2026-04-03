"""Piper TTS driver."""

import subprocess
import wave
from pathlib import Path
from typing import Any

from roamer.drivers.registry import register_driver
from roamer.drivers.speech.tts.base import TTSDriver
from roamer.output import error, success


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
            return error("tts_failed", f"Piper binary not found: {binary}")

        if not model.exists():
            return error("tts_failed", f"Piper model not found: {model}")

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
            return error("tts_failed", "Synthesis timed out")
        except FileNotFoundError:
            return error("tts_failed", "Piper binary not executable")

        if result.returncode != 0:
            stderr = result.stderr.decode() if result.stderr else "Unknown error"
            return error("tts_failed", stderr)

        path = Path(output)
        if not path.exists():
            return error("tts_failed", "Output file not created")

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
