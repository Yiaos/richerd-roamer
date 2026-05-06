"""Tests for SpeakCapability playback state integration."""

from unittest.mock import Mock, patch

from roamer.plugins.interaction.capabilities.speak import SpeakCapability
from roamer.plugins.interaction.services.playback_state import PlaybackState


def _cap(tmp_path, *, play_result=None):
    tts_driver = Mock(synthesize=Mock(return_value={"ok": True, "duration_sec": 1.0}))
    with patch(
        "roamer.plugins.interaction.capabilities.speak.get_driver",
        return_value=tts_driver,
    ):
        with patch("roamer.plugins.interaction.capabilities.speak.AudioCapability") as audio_cls:
            audio_cls.return_value.play.return_value = play_result or {"ok": True}
            cap = SpeakCapability(
                {
                    "drivers": {"tts": "edge", "audio": "alsa"},
                    "runtime": {"state_dir": str(tmp_path)},
                }
            )
            cap._create_temp_audio = Mock(return_value=str(tmp_path / "tts.wav"))
            return cap


def test_speak_marks_playback_started_and_finished(tmp_path) -> None:
    cap = _cap(tmp_path)
    state = PlaybackState(tmp_path)

    result = cap.speak("测试语音", play=True)

    assert result["ok"] is True
    assert state.is_active() is False
    assert state.generation() == 1
    snapshot = state.snapshot()
    assert snapshot["text_hash"]
    assert "测试语音" not in str(snapshot)


def test_speak_clears_playback_state_when_playback_fails(tmp_path) -> None:
    cap = _cap(
        tmp_path,
        play_result={
            "ok": False,
            "error_code": "audio.play.command_failed",
            "message": "Playback failed",
        },
    )
    state = PlaybackState(tmp_path)

    result = cap.speak("测试语音", play=True)

    assert result["ok"] is True
    assert result["played"] is False
    assert state.is_active() is False
    assert state.generation() == 1
