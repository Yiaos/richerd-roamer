"""Edge TTS driver (Microsoft cloud TTS via edge-tts)."""

import subprocess
import wave
from pathlib import Path
from typing import Any

from roamer.drivers.registry import register_driver
from roamer.drivers.speech.tts.base import TTSDriver
from roamer.output import error, success

VALID_STYLES = {
    "cheerful",
    "sad",
    "angry",
    "fearful",
    "disgruntled",
    "serious",
    "depressed",
    "embarrassed",
    "gentle",
    "lyrical",
}


class EdgeDriver(TTSDriver):
    """TTS driver using Edge TTS (Microsoft cloud voices)."""

    def synthesize(self, text: str, output: str, style: str | None = None) -> dict[str, Any]:
        """Synthesize speech using Edge TTS.

        Args:
            text: Text to synthesize
            output: Output audio file path (.mp3 or .wav)
            style: Optional emotional expression style

        Returns:
            Result dict
        """
        voice = self.config.get("voice", "zh-CN-YunxiNeural")
        rate = self.config.get("rate", "+0%")  # e.g., "+20%", "-10%"
        volume = self.config.get("volume", "+0%")

        # edge-tts outputs MP3, we may need to convert to WAV
        output_path = Path(output)
        is_wav = output_path.suffix.lower() == ".wav"

        if is_wav:
            # Generate to temp MP3 first, then convert
            mp3_output = output_path.with_suffix(".mp3")
        else:
            mp3_output = output_path

        if style and style in VALID_STYLES:
            content = (
                "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' "
                "xmlns:mstts='http://www.w3.org/2001/mstts' xml:lang='zh-CN'>"
                f"<voice name='{voice}'>"
                f"<mstts:express-as style='{style}'>{text}</mstts:express-as>"
                "</voice></speak>"
            )
            text_arg = ["--ssml", content]
        else:
            text_arg = ["--text", text]

        cmd = [
            "edge-tts",
            "--voice", voice,
            "--rate", rate,
            "--volume", volume,
            *text_arg,
            "--write-media", str(mp3_output),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            return error("tts_failed", "Edge TTS synthesis timed out")
        except FileNotFoundError:
            return error("tts_failed", "edge-tts not found. Install with: pip install edge-tts")

        if result.returncode != 0:
            if result.stderr:
                stderr = result.stderr.decode("utf-8", errors="replace")[:500]
            else:
                stderr = "Unknown error"
            return error("tts_failed", f"Edge TTS failed: {stderr}")

        if not mp3_output.exists():
            return error("tts_failed", "Output file not created")

        # Convert MP3 to WAV if needed
        if is_wav:
            convert_result = self._convert_mp3_to_wav(str(mp3_output), output)
            mp3_output.unlink(missing_ok=True)  # Clean up temp MP3
            if not convert_result["ok"]:
                return convert_result

        duration = self._get_audio_duration(output)

        return success(
            path=output,
            text=text,
            duration_sec=duration,
            voice=voice,
            style=style,
        )

    def _convert_mp3_to_wav(self, mp3_path: str, wav_path: str) -> dict[str, Any]:
        """Convert MP3 to WAV using ffmpeg."""
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output
            "-i", mp3_path,
            "-ar", "16000",  # 16kHz sample rate
            "-ac", "1",  # Mono
            wav_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            return error("tts_failed", "Audio conversion timed out")
        except FileNotFoundError:
            return error("tts_failed", "ffmpeg not found")

        if result.returncode != 0:
            return error("tts_failed", "Failed to convert audio format")

        return success()

    def _get_audio_duration(self, file: str) -> float | None:
        """Get duration of an audio file."""
        path = Path(file)

        # For WAV files, read directly
        if path.suffix.lower() == ".wav":
            try:
                with wave.open(file, "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    return frames / rate
            except Exception:
                pass

        # For MP3, use ffprobe
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                return float(result.stdout.decode().strip())
        except Exception:
            pass

        return None


# Register this driver
register_driver("tts", "edge", EdgeDriver)
