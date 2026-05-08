"""Speak capability - voice output."""

import hashlib
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

# Import drivers to register them
import roamer.plugins.interaction.drivers.speech  # noqa: F401
from roamer.platform.config import get_driver_config, get_driver_name
from roamer.platform.logging import current_request_id, log_event
from roamer.platform.output import success
from roamer.plugins.interaction.capabilities.audio import AudioCapability
from roamer.plugins.interaction.capabilities.base import Capability
from roamer.plugins.interaction.drivers.registry import get_driver
from roamer.plugins.interaction.services.playback_state import PlaybackState


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
        self._playback_state = PlaybackState.from_config(config)

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
            logging_cfg = self.config.get("logging", {})
            log_text = text if bool(logging_cfg.get("log_transcripts", True)) else ""
            log_audio_path = output if bool(logging_cfg.get("log_audio_paths", False)) else None
            log_event(
                "speak",
                "start",
                text=log_text,
                play=play,
                style=style,
                audio_path=log_audio_path,
            )
            # Synthesize
            tts_started_at = time.monotonic()
            log_event(
                "speak",
                "tts_start",
                text=log_text,
                style=style,
                audio_path=log_audio_path,
            )
            tts_result = self._tts.synthesize(text, output, style=style)
            log_event(
                "speak",
                "tts_done",
                ok=bool(tts_result.get("ok", False)),
                error_code=tts_result.get("error_code"),
                duration_sec=tts_result.get("duration_sec"),
                duration_ms=round((time.monotonic() - tts_started_at) * 1000, 3),
                audio_path=log_audio_path,
            )
            if not tts_result.get("ok"):
                return tts_result

            # Play if requested
            played = False
            if play:
                # Ensure Bluetooth speaker is connected
                self._ensure_bluetooth_connected()
                play_started_at = time.monotonic()
                playback_started = self._mark_playback_started(text)
                log_event(
                    "speak",
                    "play_start",
                    text=log_text,
                    play=True,
                    audio_path=log_audio_path,
                    playback_generation=playback_started.get("generation"),
                )
                try:
                    play_result = self._audio.play(output)
                finally:
                    playback_finished = self._mark_playback_finished(
                        playback_started.get("playback_id")
                    )
                if not play_result.get("ok"):
                    response = success(
                        text=text,
                        audio_path=output if save_path else None,
                        duration_sec=tts_result.get("duration_sec"),
                        played=False,
                        partial=True,
                        warning_code=play_result.get("error_code") or "audio.play.command_failed",
                        warning_message=play_result.get("message"),
                    )
                    log_event(
                        "speak",
                        "play_done",
                        ok=False,
                        played=False,
                        play=True,
                        error_code=play_result.get("error_code"),
                        warning_code=response.get("warning_code"),
                        duration_ms=round((time.monotonic() - play_started_at) * 1000, 3),
                        audio_path=log_audio_path,
                        playback_generation=playback_finished.get("generation"),
                    )
                    log_event(
                        "speak",
                        "playback",
                        text=log_text,
                        played=False,
                        play=True,
                        style=style,
                        duration_sec=tts_result.get("duration_sec"),
                        warning_code=response.get("warning_code"),
                        playback_generation=playback_finished.get("generation"),
                    )
                    return response
                played = True
                log_event(
                    "speak",
                    "play_done",
                    ok=True,
                    played=True,
                    play=True,
                    duration_ms=round((time.monotonic() - play_started_at) * 1000, 3),
                    audio_path=log_audio_path,
                    playback_generation=playback_finished.get("generation"),
                )

            response = success(
                text=text,
                audio_path=output if save_path else None,
                duration_sec=tts_result.get("duration_sec"),
                played=played,
            )
            log_event(
                "speak",
                "playback",
                text=log_text,
                played=played,
                play=play,
                style=style,
                duration_sec=tts_result.get("duration_sec"),
                playback_generation=self._playback_state.generation() if play else None,
            )
            return response
        finally:
            if cleanup_output and not save_path:
                try:
                    Path(output).unlink(missing_ok=True)
                except Exception:
                    pass

    def _mark_playback_started(self, text: str) -> dict[str, Any]:
        try:
            return self._playback_state.mark_started(
                request_id=current_request_id(),
                source="speak",
                text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
            )
        except OSError as exc:
            log_event(
                "speak",
                "playback_state_unavailable",
                operation="mark_started",
                error=str(exc),
            )
            return {"generation": None}

    def _mark_playback_finished(self, playback_id: str | None) -> dict[str, Any]:
        if not playback_id:
            return {"generation": None}
        try:
            return self._playback_state.mark_finished(
                playback_id=playback_id,
                source="speak",
            )
        except OSError as exc:
            log_event(
                "speak",
                "playback_state_unavailable",
                operation="mark_finished",
                error=str(exc),
            )
            return {"generation": None}
