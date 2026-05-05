"""ALSA audio driver using arecord/aplay."""

import subprocess
import wave
from pathlib import Path
from typing import Any, Iterator

from roamer.platform.contract import ErrorCode
from roamer.platform.output import error, success
from roamer.plugins.interaction.drivers.audio.base import AudioDriver
from roamer.plugins.interaction.drivers.registry import register_driver


class AlsaDriver(AudioDriver):
    """Audio driver using ALSA tools (arecord/aplay)."""

    def stream_chunks(
        self,
        *,
        chunk_duration_sec: float = 0.032,
        max_duration_sec: float | None = 10.0,
    ) -> Iterator[bytes]:
        """Stream raw PCM chunks from arecord stdout.

        This is intentionally separate from ``record`` so the existing file
        recording/audio.record path stays byte-for-byte compatible with the
        prior arecord-to-file behavior.
        """
        device = self.config.get("capture_device", "default")
        sample_rate = int(self.config.get("sample_rate", 16000))
        channels = int(self.config.get("channels", 2))
        sample_width_bytes = 2
        chunk_size = max(1, int(sample_rate * chunk_duration_sec))
        read_size = chunk_size * channels * sample_width_bytes

        cmd = [
            "arecord",
            "-D",
            str(device),
            "-f",
            "S16_LE",
            "-r",
            str(sample_rate),
            "-c",
            str(channels),
            "-t",
            "raw",
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        emitted = 0
        max_chunks = (
            None
            if max_duration_sec is None
            else max(1, int(max_duration_sec / chunk_duration_sec) + 1)
        )

        try:
            if process.stdout is None:
                raise RuntimeError("arecord stdout unavailable")
            while max_chunks is None or emitted < max_chunks:
                chunk = process.stdout.read(read_size)
                if not chunk:
                    break
                emitted += 1
                yield chunk
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1)

    def record(self, output: str, duration: float) -> dict[str, Any]:
        """Record audio using arecord.

        Args:
            output: Output file path
            duration: Recording duration in seconds

        Returns:
            Result dict
        """
        device = self.config.get("capture_device", "default")
        sample_rate = self.config.get("sample_rate", 16000)
        channels = self.config.get("channels", 2)

        cmd = [
            "arecord",
            "-D",
            device,
            "-f",
            "S16_LE",
            "-r",
            str(sample_rate),
            "-c",
            str(channels),
            "-d",
            str(int(duration)),
            output,
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, timeout=duration + 5
            )
        except subprocess.TimeoutExpired:
            return error(
                "audio_record_failed",
                "Recording timed out",
                error_code=ErrorCode.AUDIO_RECORD_TIMEOUT,
            )
        except FileNotFoundError:
            return error(
                "audio_record_failed",
                "arecord not installed",
                error_code=ErrorCode.DEPENDENCY_AUDIO_ARECORD_MISSING,
            )

        if result.returncode != 0:
            stderr = "Unknown error"
            if result.stderr:
                stderr = result.stderr.decode("utf-8", errors="replace").strip()[:500]
            return error(
                "audio_record_failed",
                "Recording failed",
                details=stderr,
                error_code=ErrorCode.AUDIO_RECORD_COMMAND_FAILED,
            )

        path = Path(output)
        if not path.exists():
            return error(
                "audio_record_failed",
                "Output file not created",
                error_code=ErrorCode.AUDIO_RECORD_OUTPUT_MISSING,
            )

        return success(
            path=output,
            duration_sec=duration,
            sample_rate=sample_rate,
            channels=channels,
            size_bytes=path.stat().st_size,
        )

    def play(self, file: str) -> dict[str, Any]:
        """Play audio using aplay.

        Args:
            file: Audio file path

        Returns:
            Result dict
        """
        device = self.config.get("playback_device", "default")

        # Get duration from file
        duration = self._get_wav_duration(file)

        cmd = ["aplay", "-D", device, file]

        try:
            timeout = duration + 5 if duration else 60
            result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return error(
                "audio_play_failed",
                "Playback timed out",
                error_code=ErrorCode.AUDIO_PLAY_TIMEOUT,
            )
        except FileNotFoundError:
            return error(
                "audio_play_failed",
                "aplay not installed",
                error_code=ErrorCode.DEPENDENCY_AUDIO_APLAY_MISSING,
            )

        if result.returncode != 0:
            stderr = "Unknown error"
            if result.stderr:
                stderr = result.stderr.decode("utf-8", errors="replace").strip()[:500]
            return error(
                "audio_play_failed",
                "Playback failed",
                details=stderr,
                error_code=ErrorCode.AUDIO_PLAY_COMMAND_FAILED,
            )

        return success(
            played=file,
            duration_sec=duration,
        )

    def _get_wav_duration(self, file: str) -> float | None:
        """Get duration of a WAV file.

        Args:
            file: WAV file path

        Returns:
            Duration in seconds, or None if cannot be determined
        """
        try:
            with wave.open(file, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                return frames / rate
        except Exception:
            return None


# Register this driver
register_driver("audio", "alsa", AlsaDriver)
