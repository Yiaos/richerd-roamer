"""Tests for runtime logging integration across interaction capabilities."""

from __future__ import annotations

from unittest.mock import Mock, patch

import numpy as np

from roamer.plugins.interaction.capabilities.converse import ConverseCapability
from roamer.plugins.interaction.capabilities.listen import ListenCapability
from roamer.plugins.interaction.capabilities.speak import SpeakCapability
from roamer.plugins.interaction.capabilities.wake import WakeCapability
from roamer.plugins.interaction.services.serve import RoamerServeRuntime


def _converse_config() -> dict:
    return {
        "converse": {
            "wakeword": {"phrases": ["richard", "瑞彻德"], "min_interval_sec": 0},
            "intents": [{"name": "time_now", "action": "time.now", "patterns": ["几点"]}],
            "discord": {"enabled": False, "channel_id": "", "token_env": "DISCORD_BOT_TOKEN"},
        }
    }


def test_wake_logs_transcript_and_match(monkeypatch) -> None:
    events = []
    cap = WakeCapability(_converse_config())
    cap._wait_for_trigger = Mock(return_value=True)
    cap._start_preroll_source_if_needed = Mock(return_value=None)
    cap._listen_once = Mock(return_value={"ok": True, "text": "瑞彻德 现在几点了"})
    cap._route_text = Mock(return_value={"turn_id": 1, "route": "local", "action": "time.now"})
    monkeypatch.setattr(
        "roamer.plugins.interaction.capabilities.wake.log_event",
        lambda component, event, **fields: events.append((component, event, fields)),
    )

    result = cap.run(once=True, timeout=1.0, no_sound=True)

    assert result["ok"] is True
    assert ("wake", "asr_transcript") == events[0][:2]
    assert events[0][2]["text"] == "瑞彻德 现在几点了"
    assert events[0][2]["matched"] is True
    assert events[0][2]["command_text"] == "现在几点了"


def test_wake_respects_log_transcripts_setting(monkeypatch) -> None:
    events = []
    config = _converse_config()
    config["logging"] = {"log_transcripts": False}
    cap = WakeCapability(config)
    cap._wait_for_trigger = Mock(return_value=True)
    cap._start_preroll_source_if_needed = Mock(return_value=None)
    cap._listen_once = Mock(return_value={"ok": True, "text": "瑞彻德 现在几点了"})
    cap._route_text = Mock(return_value={"turn_id": 1, "route": "local", "action": "time.now"})
    monkeypatch.setattr(
        "roamer.plugins.interaction.capabilities.wake.log_event",
        lambda component, event, **fields: events.append((component, event, fields)),
    )

    result = cap.run(once=True, timeout=1.0, no_sound=True)

    assert result["ok"] is True
    assert events[0][2]["text"] == ""
    assert events[0][2]["command_text"] == ""


def test_wake_does_not_log_empty_transcript(monkeypatch) -> None:
    events = []
    cap = WakeCapability(_converse_config())
    cap._wait_for_trigger = Mock(return_value=True)
    cap._start_preroll_source_if_needed = Mock(return_value=None)
    cap._listen_once = Mock(return_value={"ok": True, "text": "   "})
    monkeypatch.setattr(
        "roamer.plugins.interaction.capabilities.wake.log_event",
        lambda component, event, **fields: events.append((component, event, fields)),
    )

    result = cap.run(once=True, timeout=1.0, no_sound=True)

    assert result["ok"] is True
    assert events == []


def test_converse_logs_route_decision(monkeypatch) -> None:
    events = []
    cap = ConverseCapability(_converse_config())
    monkeypatch.setattr(
        "roamer.plugins.interaction.capabilities.converse.log_event",
        lambda component, event, **fields: events.append((component, event, fields)),
    )

    turn = cap.route_text("现在几点", session_id="s1", turn_id=1, no_sound=True)

    assert turn["route"] == "local"
    assert ("converse", "route_text") == events[0][:2]
    assert events[0][2]["text"] == "现在几点"
    assert events[0][2]["route"] == "local"
    assert events[0][2]["action"] == "time.now"


def test_converse_respects_log_transcripts_setting(monkeypatch) -> None:
    events = []
    config = _converse_config()
    config["logging"] = {"log_transcripts": False}
    cap = ConverseCapability(config)
    monkeypatch.setattr(
        "roamer.plugins.interaction.capabilities.converse.log_event",
        lambda component, event, **fields: events.append((component, event, fields)),
    )

    turn = cap.route_text("现在几点", session_id="s1", turn_id=1, no_sound=True)

    assert turn["route"] == "local"
    assert events[0][2]["text"] == ""


def test_listen_logs_asr_transcript(monkeypatch, tmp_path) -> None:
    events = []
    cap = ListenCapability.__new__(ListenCapability)
    cap.config = {}
    cap._vad = Mock(
        detect=Mock(
            return_value={
                "ok": True,
                "speech_detected": True,
                "segments": [{"start": 0.0, "end": 0.2}],
            }
        )
    )
    cap._asr = Mock(transcribe=Mock(return_value={"ok": True, "text": "瑞彻德", "confidence": 0.8}))
    cap._create_temp_audio = Mock(return_value=str(tmp_path / "trimmed.wav"))
    cap._load_wav = Mock(return_value=(np.ones(3200, dtype=np.float32), 16000))
    cap._save_wav = Mock()
    monkeypatch.setattr(
        "roamer.plugins.interaction.capabilities.listen.log_event",
        lambda component, event, **fields: events.append((component, event, fields)),
    )

    result = cap.transcribe_audio_file(str(tmp_path / "input.wav"))

    assert result["ok"] is True
    assert ("listen", "asr_transcript") == events[0][:2]
    assert events[0][2]["text"] == "瑞彻德"


def test_listen_does_not_log_empty_asr_transcript(monkeypatch, tmp_path) -> None:
    events = []
    cap = ListenCapability.__new__(ListenCapability)
    cap.config = {}
    cap._vad = Mock(
        detect=Mock(
            return_value={
                "ok": True,
                "speech_detected": True,
                "segments": [{"start": 0.0, "end": 0.2}],
            }
        )
    )
    cap._asr = Mock(transcribe=Mock(return_value={"ok": True, "text": "   ", "confidence": 0.0}))
    cap._create_temp_audio = Mock(return_value=str(tmp_path / "trimmed.wav"))
    cap._load_wav = Mock(return_value=(np.ones(3200, dtype=np.float32), 16000))
    cap._save_wav = Mock()
    monkeypatch.setattr(
        "roamer.plugins.interaction.capabilities.listen.log_event",
        lambda component, event, **fields: events.append((component, event, fields)),
    )

    result = cap.transcribe_audio_file(str(tmp_path / "input.wav"))

    assert result["ok"] is True
    assert result["text"] == "   "
    assert events == []


def test_speak_logs_playback_result(monkeypatch, tmp_path) -> None:
    events = []
    tts_driver = Mock(synthesize=Mock(return_value={"ok": True, "duration_sec": 1.0}))
    monkeypatch.setattr(
        "roamer.plugins.interaction.capabilities.speak.get_driver",
        lambda kind, name, cfg: tts_driver,
    )
    with patch("roamer.plugins.interaction.capabilities.speak.AudioCapability") as audio_cls:
        audio_cls.return_value.play.return_value = {"ok": True}
        cap = SpeakCapability({"drivers": {"tts": "edge", "audio": "alsa"}})
        cap._create_temp_audio = Mock(return_value=str(tmp_path / "tts.wav"))
        monkeypatch.setattr(
            "roamer.plugins.interaction.capabilities.speak.log_event",
            lambda component, event, **fields: events.append((component, event, fields)),
        )

        result = cap.speak("测试语音", play=True)

    assert result["ok"] is True
    assert ("speak", "playback") == events[0][:2]
    assert events[0][2]["text"] == "测试语音"
    assert events[0][2]["played"] is True


def test_speak_respects_log_transcripts_setting(monkeypatch, tmp_path) -> None:
    events = []
    tts_driver = Mock(synthesize=Mock(return_value={"ok": True, "duration_sec": 1.0}))
    monkeypatch.setattr(
        "roamer.plugins.interaction.capabilities.speak.get_driver",
        lambda kind, name, cfg: tts_driver,
    )
    with patch("roamer.plugins.interaction.capabilities.speak.AudioCapability") as audio_cls:
        audio_cls.return_value.play.return_value = {"ok": True}
        cap = SpeakCapability(
            {
                "drivers": {"tts": "edge", "audio": "alsa"},
                "logging": {"log_transcripts": False},
            }
        )
        cap._create_temp_audio = Mock(return_value=str(tmp_path / "tts.wav"))
        monkeypatch.setattr(
            "roamer.plugins.interaction.capabilities.speak.log_event",
            lambda component, event, **fields: events.append((component, event, fields)),
        )

        result = cap.speak("测试语音", play=True)

    assert result["ok"] is True
    assert events[0][2]["text"] == ""


def test_serve_runtime_logs_request(monkeypatch) -> None:
    events = []
    runtime = RoamerServeRuntime({})
    monkeypatch.setattr(
        "roamer.plugins.interaction.services.serve.log_event",
        lambda component, event, **fields: events.append((component, event, fields)),
    )

    result = runtime.handle({"command": "ping", "args": {"token": "abc123SECRETxyz789"}})

    assert result["ok"] is True
    assert ("serve", "request") == events[0][:2]
    assert events[0][2]["command"] == "ping"
    assert events[0][2]["ok"] is True


def test_serve_runtime_sets_request_id_for_nested_actions(monkeypatch) -> None:
    from roamer.platform.logging import current_request_id

    request_ids = []
    runtime = RoamerServeRuntime(
        {
            "converse": {
                "endpoint": {"mode": "fixed"},
            }
        }
    )
    monkeypatch.setattr(runtime, "ensure_registered", lambda: None)
    monkeypatch.setattr(
        "roamer.plugins.interaction.services.serve.run_action",
        lambda _name, **_kwargs: request_ids.append(current_request_id()) or {"ok": True},
    )

    result = runtime.handle({"command": "converse", "request_id": "req-serve-1", "args": {}})

    assert result["ok"] is True
    assert result["request_id"] == "req-serve-1"
    assert request_ids == ["req-serve-1"]
