"""Tests for runtime logging integration across interaction capabilities."""

from __future__ import annotations

from unittest.mock import Mock, patch

import numpy as np

from roamer.platform.logging import current_request_id, request_context
from roamer.plugins.interaction.capabilities.audio import AudioCapability
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


def _event(events: list, name: str) -> tuple:
    for item in events:
        if item[1] == name:
            return item
    raise AssertionError(f"missing event {name}; got {[item[1] for item in events]}")


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
    assert _event(events, "trigger_wait_start")[0] == "wake"
    assert _event(events, "trigger_hit")[0] == "wake"
    assert _event(events, "listen_start")[2]["level"] == "DEBUG"
    assert _event(events, "listen_done")[2]["level"] == "DEBUG"
    assert _event(events, "listen_done")[2]["ok"] is True
    asr_event = _event(events, "asr_transcript")
    assert ("wake", "asr_transcript") == asr_event[:2]
    assert asr_event[2]["text"] == "瑞彻德 现在几点了"
    assert asr_event[2]["matched"] is True
    assert asr_event[2]["command_text"] == "现在几点了"
    assert _event(events, "route_start")[2]["text"] == "现在几点了"
    assert _event(events, "route_done")[2]["ok"] is True


def test_wake_preserves_existing_request_context(monkeypatch) -> None:
    request_ids = []
    cap = WakeCapability(_converse_config())
    cap._wait_for_trigger = Mock(return_value=True)
    cap._start_preroll_source_if_needed = Mock(return_value=None)

    def _listen_once(**_kwargs):
        request_ids.append(("listen", current_request_id()))
        return {"ok": True, "text": "瑞彻德 现在几点了"}

    def _route_text(**_kwargs):
        request_ids.append(("route", current_request_id()))
        return {"turn_id": 1, "route": "local", "action": "time.now"}

    cap._listen_once = Mock(side_effect=_listen_once)
    cap._route_text = Mock(side_effect=_route_text)

    with request_context("req-wake-parent"):
        result = cap.run(once=True, timeout=1.0, no_sound=True)

    assert result["ok"] is True
    assert request_ids == [
        ("listen", "req-wake-parent"),
        ("route", "req-wake-parent"),
    ]


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
    asr_event = _event(events, "asr_transcript")
    assert asr_event[2]["text"] == ""
    assert asr_event[2]["command_text"] == ""


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
    assert all(event != "asr_transcript" for _component, event, _fields in events)
    ignored = _event(events, "route_ignored")
    assert ignored[2]["reason"] == "empty_transcript"
    assert ignored[2]["text"] == ""


def test_wake_logs_unmatched_transcript_as_ignored(monkeypatch) -> None:
    events = []
    cap = WakeCapability(_converse_config())
    cap._wait_for_trigger = Mock(return_value=True)
    cap._start_preroll_source_if_needed = Mock(return_value=None)
    cap._listen_once = Mock(
        side_effect=[
            {"ok": True, "text": "车的，现在几点了？"},
            {"ok": True, "text": "瑞彻德 现在几点了"},
        ]
    )
    cap._route_text = Mock(return_value={"turn_id": 1, "route": "local", "action": "time.now"})
    monkeypatch.setattr(
        "roamer.plugins.interaction.capabilities.wake.log_event",
        lambda component, event, **fields: events.append((component, event, fields)),
    )

    result = cap.run(once=True, timeout=1.0, no_sound=True)

    assert result["ok"] is True
    ignored = _event(events, "route_ignored")
    assert ignored[2]["reason"] == "wake_phrase_not_matched"
    assert ignored[2]["text"] == "车的，现在几点了？"
    assert ignored[2]["matched"] is False
    assert ignored[2]["in_followup"] is False


def test_wake_logs_wake_phrase_only_as_ignored(monkeypatch) -> None:
    events = []
    cap = WakeCapability(_converse_config())
    cap._wait_for_trigger = Mock(return_value=True)
    cap._start_preroll_source_if_needed = Mock(return_value=None)
    cap._listen_once = Mock(
        side_effect=[
            {"ok": True, "text": "瑞彻德"},
            {"ok": True, "text": "现在几点了"},
        ]
    )
    cap._route_text = Mock(return_value={"turn_id": 1, "route": "local", "action": "time.now"})
    monkeypatch.setattr(
        "roamer.plugins.interaction.capabilities.wake.log_event",
        lambda component, event, **fields: events.append((component, event, fields)),
    )

    result = cap.run(once=True, timeout=1.0, no_sound=True)

    assert result["ok"] is True
    ignored = _event(events, "route_ignored")
    assert ignored[2]["reason"] == "wake_phrase_only"
    assert ignored[2]["matched"] is True
    assert ignored[2]["in_followup"] is False


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
    assert _event(events, "vad_start")[0] == "listen"
    assert _event(events, "vad_done")[2]["speech_detected"] is True
    assert _event(events, "asr_start")[0] == "listen"
    assert _event(events, "asr_done")[2]["ok"] is True
    transcript = _event(events, "asr_transcript")
    assert ("listen", "asr_transcript") == transcript[:2]
    assert transcript[2]["text"] == "瑞彻德"


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
    assert _event(events, "asr_done")[2]["ok"] is True
    assert all(event != "asr_transcript" for _component, event, _fields in events)


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
    assert _event(events, "start")[2]["text"] == "测试语音"
    assert _event(events, "tts_start")[2]["text"] == "测试语音"
    assert _event(events, "tts_done")[2]["duration_sec"] == 1.0
    assert _event(events, "play_start")[2]["play"] is True
    assert _event(events, "play_done")[2]["played"] is True
    playback = _event(events, "playback")
    assert ("speak", "playback") == playback[:2]
    assert playback[2]["text"] == "测试语音"
    assert playback[2]["played"] is True


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
    assert _event(events, "start")[2]["text"] == ""
    assert _event(events, "playback")[2]["text"] == ""


def test_audio_logs_record_play_and_stream_lifecycle(monkeypatch) -> None:
    events = []
    cap = AudioCapability.__new__(AudioCapability)
    cap.config = {}
    cap._driver = Mock()
    cap._driver.record.return_value = {"ok": True, "path": "/tmp/a.wav", "duration_sec": 1.0}
    cap._driver.play.return_value = {"ok": True, "played": "/tmp/a.wav"}
    cap._driver.stream_chunks.return_value = iter([b"one", b"two"])
    monkeypatch.setattr(
        "roamer.plugins.interaction.capabilities.audio.log_event",
        lambda component, event, **fields: events.append((component, event, fields)),
    )

    assert cap.record(duration=1.0, output="/tmp/a.wav")["ok"] is True
    assert cap.play("/tmp/a.wav")["ok"] is True
    assert list(cap.stream_chunks(chunk_duration_sec=0.1, max_duration_sec=0.2)) == [
        b"one",
        b"two",
    ]

    assert _event(events, "record_start")[0] == "audio"
    assert _event(events, "record_done")[2]["ok"] is True
    assert _event(events, "play_start")[0] == "audio"
    assert _event(events, "play_done")[2]["ok"] is True
    assert _event(events, "stream_start")[0] == "audio"
    assert _event(events, "stream_done")[2]["chunk_count"] == 2


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
