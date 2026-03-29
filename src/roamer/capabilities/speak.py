"""Speak capability - voice output."""

import os
import tempfile
from pathlib import Path
from typing import Any

# Import drivers to register them
import roamer.drivers.speech  # noqa: F401
from roamer.capabilities._audio import AudioCapability
from roamer.capabilities.base import Capability
from roamer.config import get_driver_config, get_driver_name
from roamer.drivers.registry import get_driver
from roamer.output import success


class SpeakCapability(Capability):
    """Speak capability - text to speech output."""

    def __init__(self, config: dict[str, Any]):
        """Initialize speak capability.

        Args:
            config: Full configuration dictionary
        """
        super().__init__(config)

        # Load TTS driver
        tts_name = get_driver_name(config, "tts")
        tts_config = get_driver_config(config, tts_name)
        self._tts = get_driver("tts", tts_name, tts_config)

        # Audio capability for playback
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

    def speak(
        self,
        text: str,
        save_path: str | None = None,
        play: bool = True,
    ) -> dict[str, Any]:
        """Text to speech.

        Args:
            text: Text to speak
            save_path: Optional path to save audio
            play: Whether to play the audio

        Returns:
            Result dict with text, audio_path, duration_sec, played
        """
        output = save_path if save_path else self._create_temp_audio("roamer_tts_")
        cleanup_output = save_path is None

        try:
            # Synthesize
            tts_result = self._tts.synthesize(text, output)
            if not tts_result.get("ok"):
                return tts_result

            # Play if requested
            played = False
            if play:
                play_result = self._audio.play(output)
                played = play_result.get("ok", False)

            return success(
                text=text,
                audio_path=output if save_path else None,
                duration_sec=tts_result.get("duration_sec"),
                played=played,
            )
        finally:
            if cleanup_output and not save_path:
                try:
                    Path(output).unlink(missing_ok=True)
                except Exception:
                    pass
