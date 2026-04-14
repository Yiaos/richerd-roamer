"""Speak capability - voice output."""

import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

# Import drivers to register them
import roamer.plugins.interaction.drivers.speech  # noqa: F401
from roamer.platform.config import get_driver_config, get_driver_name
from roamer.platform.output import success
from roamer.plugins.interaction.capabilities.audio import AudioCapability
from roamer.plugins.interaction.capabilities.base import Capability
from roamer.plugins.interaction.drivers.registry import get_driver


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

        # Bluetooth speaker config
        bt_config = config.get("bluetooth", {})
        self._bt_speaker_mac = bt_config.get("speaker_mac")

    def _has_bluetooth_sink(self) -> bool:
        """Check if a Bluetooth audio sink exists in PulseAudio."""
        try:
            result = subprocess.run(
                ["pactl", "list", "sinks", "short"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return "bluez_sink" in result.stdout
        except Exception:
            return False

    def _ensure_bluetooth_connected(self, max_wait: float = 8.0) -> bool:
        """Ensure Bluetooth speaker is connected.

        Args:
            max_wait: Maximum seconds to wait for connection

        Returns:
            True if Bluetooth sink is available
        """
        # Already have a sink?
        if self._has_bluetooth_sink():
            return True

        # No MAC configured, can't auto-connect
        if not self._bt_speaker_mac:
            return False

        # Try to connect
        try:
            subprocess.run(
                ["bluetoothctl", "connect", self._bt_speaker_mac],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            return False

        # Wait for sink to appear
        start = time.time()
        while time.time() - start < max_wait:
            if self._has_bluetooth_sink():
                return True
            time.sleep(0.5)

        return self._has_bluetooth_sink()

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
        style: str | None = None,
    ) -> dict[str, Any]:
        """Text to speech.

        Args:
            text: Text to speak
            save_path: Optional path to save audio
            play: Whether to play the audio
            style: Optional emotional expression style

        Returns:
            Result dict with text, audio_path, duration_sec, played
        """
        output = save_path if save_path else self._create_temp_audio("roamer_tts_")
        cleanup_output = save_path is None

        try:
            # Synthesize
            tts_result = self._tts.synthesize(text, output, style=style)
            if not tts_result.get("ok"):
                return tts_result

            # Play if requested
            played = False
            if play:
                # Ensure Bluetooth speaker is connected
                self._ensure_bluetooth_connected()
                play_result = self._audio.play(output)
                if not play_result.get("ok"):
                    return success(
                        text=text,
                        audio_path=output if save_path else None,
                        duration_sec=tts_result.get("duration_sec"),
                        played=False,
                        partial=True,
                        warning_code=play_result.get("error_code") or "audio.play.command_failed",
                        warning_message=play_result.get("message"),
                    )
                played = True

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
