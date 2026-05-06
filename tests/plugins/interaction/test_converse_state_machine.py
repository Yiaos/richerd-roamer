"""Tests for converse capability state-machine behavior."""

from unittest.mock import patch

from roamer.platform.contract import ErrorCode
from roamer.plugins.interaction.capabilities.converse import ConverseCapability


def _base_config() -> dict:
    return {
        "converse": {
            "silence_timeout": 0.1,
            "max_turns": 3,
            "wakeword": {"enabled": True, "driver": "openwakeword", "model": "", "threshold": 0.5},
            "intents": [
                {"name": "time_now", "action": "time.now", "patterns": ["几点"]},
            ],
            "discord": {
                "enabled": False,
                "channel_id": "",
                "token_env": "DISCORD_BOT_TOKEN",
                "source": "roamer",
            },
        }
    }


def test_converse_r1_no_wakeword_local_intent_then_exit() -> None:
    cap = ConverseCapability(_base_config())

    listen_seq = [
        {"ok": True, "text": "现在几点"},
        {"ok": True, "text": ""},
    ]

    def _run_action(name: str, **kwargs):
        if name == "listen":
            return listen_seq.pop(0)
        if name == "speak":
            return {"ok": True, "played": True}
        return {"ok": True}

    with patch(
        "roamer.plugins.interaction.capabilities.converse.run_action", side_effect=_run_action
    ):
        result = cap.run(no_wakeword=True, timeout=0.1, no_sound=True, max_turns=3)

    assert result["ok"] is True
    assert result["completed"] is True
    assert result["mode"] == "no_wakeword"
    assert len(result["turns"]) >= 1
    assert result["turns"][0]["matched"] is True


def test_converse_r1_no_wakeword_fallback_route() -> None:
    cap = ConverseCapability(_base_config())

    listen_seq = [
        {"ok": True, "text": "讲个笑话"},
        {"ok": True, "text": ""},
    ]

    def _run_action(name: str, **kwargs):
        if name == "listen":
            return listen_seq.pop(0)
        return {"ok": True}

    with patch(
        "roamer.plugins.interaction.capabilities.converse.run_action", side_effect=_run_action
    ):
        with patch(
            "roamer.plugins.interaction.capabilities.converse.send_fallback",
            return_value={"ok": True, "sent": False, "skipped": True},
        ):
            result = cap.run(no_wakeword=True, timeout=0.1, no_sound=True, max_turns=2)

    assert result["ok"] is True
    assert result["turns"][0]["route"] == "discord"


def test_converse_route_text_reuses_local_intent_flow() -> None:
    cap = ConverseCapability(_base_config())

    with patch(
        "roamer.plugins.interaction.capabilities.converse.run_action",
        return_value={"ok": True, "played": True},
    ):
        result = cap.route_text(
            "现在几点",
            session_id="s1",
            turn_id=1,
            no_sound=True,
        )

    assert result["turn_id"] == 1
    assert result["text"] == "现在几点"
    assert result["matched"] is True
    assert result["route"] == "local"
    assert result["action"] == "time.now"


def test_converse_logs_route_before_local_side_effect(monkeypatch) -> None:
    events = []
    order = []
    cap = ConverseCapability(_base_config())
    monkeypatch.setattr(
        "roamer.plugins.interaction.capabilities.converse.log_event",
        lambda component, event, **fields: events.append((component, event, fields))
        or order.append(event),
    )

    def _run_action(name: str, **_kwargs):
        order.append(name)
        return {"ok": True, "played": True}

    with patch(
        "roamer.plugins.interaction.capabilities.converse.run_action",
        side_effect=_run_action,
    ):
        result = cap.route_text("现在几点", session_id="s1", turn_id=1, no_sound=False)

    assert result["route"] == "local"
    assert order[0] == "route_text"
    assert order[1] == "speak"
    assert events[0][2]["route"] == "local"
    assert events[0][2]["action"] == "time.now"


def test_converse_logs_route_before_discord_fallback(monkeypatch) -> None:
    events = []
    order = []
    cap = ConverseCapability(_base_config())
    monkeypatch.setattr(
        "roamer.plugins.interaction.capabilities.converse.log_event",
        lambda component, event, **fields: events.append((component, event, fields))
        or order.append(event),
    )

    def _send_fallback(*_args, **_kwargs):
        order.append("send_fallback")
        return {"ok": True, "sent": True}

    with patch(
        "roamer.plugins.interaction.capabilities.converse.send_fallback",
        side_effect=_send_fallback,
    ):
        result = cap.route_text("讲个笑话", session_id="s1", turn_id=1, no_sound=True)

    assert result["route"] == "discord"
    assert order[0] == "route_text"
    assert order[1] == "send_fallback"
    assert events[0][2]["route"] == "discord"


def test_converse_route_text_reuses_discord_fallback_flow() -> None:
    cap = ConverseCapability(_base_config())

    with patch(
        "roamer.plugins.interaction.capabilities.converse.send_fallback",
        side_effect=lambda text, *, config, session_id, turn_id, timeout_sec: {
            "ok": True,
            "sent": False,
            "skipped": True,
            "logging": config.get("logging"),
        },
    ):
        result = cap.route_text(
            "讲个笑话",
            session_id="s1",
            turn_id=1,
            no_sound=True,
        )

    assert result["route"] == "discord"
    assert result["matched"] is False
    assert result["fallback"]["logging"] == {}


def test_converse_route_text_propagates_discord_fallback_failure() -> None:
    cap = ConverseCapability(_base_config())

    with patch(
        "roamer.plugins.interaction.capabilities.converse.send_fallback",
        return_value={
            "ok": False,
            "error": "converse_discord_send_failed",
            "message": "missing token",
            "error_code": ErrorCode.CONVERSE_DISCORD_SEND_FAILED,
        },
    ):
        result = cap.route_text(
            "讲个笑话",
            session_id="s1",
            turn_id=1,
            no_sound=True,
        )

    assert result["ok"] is False
    assert result["route"] == "discord"
    assert result["error_code"] == ErrorCode.CONVERSE_DISCORD_SEND_FAILED


def test_converse_run_returns_error_when_discord_fallback_fails() -> None:
    cap = ConverseCapability(_base_config())

    with patch(
        "roamer.plugins.interaction.capabilities.converse.run_action",
        return_value={"ok": True, "text": "讲个笑话"},
    ):
        with patch(
            "roamer.plugins.interaction.capabilities.converse.send_fallback",
            return_value={
                "ok": False,
                "error": "converse_discord_send_failed",
                "message": "missing token",
                "error_code": ErrorCode.CONVERSE_DISCORD_SEND_FAILED,
            },
        ):
            result = cap.run(no_wakeword=True, timeout=0.1, no_sound=True, max_turns=1)

    assert result["ok"] is False
    assert result["error_code"] == ErrorCode.CONVERSE_DISCORD_SEND_FAILED
    assert result["turns"][0]["route"] == "discord"


def test_converse_route_text_can_suppress_discord_fallback() -> None:
    cap = ConverseCapability(_base_config())

    with patch("roamer.plugins.interaction.capabilities.converse.send_fallback") as fallback:
        result = cap.route_text(
            "嗯",
            session_id="s1",
            turn_id=1,
            no_sound=True,
            allow_fallback=False,
        )

    assert result["route"] == "ignored"
    assert result["matched"] is False
    assert result["reason"] == "fallback_disabled"
    fallback.assert_not_called()


def test_converse_listen_failure_returns_canonical_error() -> None:
    cap = ConverseCapability(_base_config())

    with patch(
        "roamer.plugins.interaction.capabilities.converse.run_action",
        return_value={"ok": False, "error_code": "audio.record.timeout"},
    ):
        result = cap.run(no_wakeword=True, timeout=0.1, no_sound=True, max_turns=1)

    assert result["ok"] is False
    assert result["error_code"] == ErrorCode.CONVERSE_LISTEN_FAILED


def test_converse_wakeword_mode_driver_unavailable() -> None:
    cap = ConverseCapability(_base_config())

    with patch(
        "roamer.plugins.interaction.capabilities.converse.get_driver",
        side_effect=RuntimeError("no driver"),
    ):
        result = cap.run(no_wakeword=False, timeout=0.1, no_sound=True, max_turns=1)

    assert result["ok"] is False
    assert result["error_code"] == ErrorCode.CONVERSE_WAKEWORD_UNAVAILABLE


def test_converse_wakeword_timeout_returns_completed_without_turns() -> None:
    cap = ConverseCapability(_base_config())

    class _Driver:
        def start(self):
            return None

        def stop(self):
            return None

        def wait_hit(self, timeout: float):
            return False

    with patch(
        "roamer.plugins.interaction.capabilities.converse.get_driver", return_value=_Driver()
    ):
        result = cap.run(no_wakeword=False, timeout=0.1, no_sound=True, max_turns=1)

    assert result["ok"] is True
    assert result["reason"] == "wakeword_timeout"
    assert result["turns"] == []


def test_converse_endpointing_flag_forwards_endpoint_metrics() -> None:
    config = _base_config()
    cap = ConverseCapability(config)
    calls = []

    def _run_action(name: str, **kwargs):
        calls.append((name, kwargs))
        if name == "listen":
            return {
                "ok": True,
                "text": "现在几点",
                "endpoint_metrics": {
                    "record_duration_sec": 0.8,
                    "speech_duration_sec": 0.3,
                    "endpoint_latency_sec": 0.2,
                },
            }
        if name == "speak":
            return {"ok": True, "played": True}
        return {"ok": True}

    with patch(
        "roamer.plugins.interaction.capabilities.converse.run_action", side_effect=_run_action
    ):
        result = cap.run(
            no_wakeword=True,
            timeout=1.0,
            no_sound=True,
            max_turns=1,
            use_endpointing=True,
        )

    assert result["ok"] is True
    listen_calls = [kwargs for name, kwargs in calls if name == "listen"]
    assert listen_calls == [
        {"timeout": 1.0, "save_audio": None, "debug": False, "use_endpointing": True}
    ]
    assert result["turns"][0]["endpoint_metrics"] == {
        "record_duration_sec": 0.8,
        "speech_duration_sec": 0.3,
        "endpoint_latency_sec": 0.2,
    }


def test_converse_endpointing_listen_failure_forwards_top_level_metrics() -> None:
    config = _base_config()
    cap = ConverseCapability(config)
    metrics = {"record_duration_sec": 0.5, "speech_duration_sec": 0.0}

    with patch(
        "roamer.plugins.interaction.capabilities.converse.run_action",
        return_value={
            "ok": False,
            "error_code": "speech.vad.no_speech",
            "endpoint_metrics": metrics,
        },
    ):
        result = cap.run(no_wakeword=True, no_sound=True, max_turns=1, use_endpointing=True)

    assert result["ok"] is False
    assert result["endpoint_metrics"] == metrics
    assert result["turns"][0]["endpoint_metrics"] == metrics


def test_converse_r1_spoken_reminder_routes_to_remind_schedule() -> None:
    cap = ConverseCapability(_base_config())
    calls = []

    def _run_action(name: str, **kwargs):
        calls.append((name, kwargs))
        if name == "listen":
            return {"ok": True, "text": "十秒后提醒我喝水"}
        if name == "remind":
            return {"ok": True, "scheduled": True, **kwargs}
        if name == "speak":
            return {"ok": True, "played": True}
        return {"ok": True}

    with patch(
        "roamer.plugins.interaction.capabilities.converse.run_action", side_effect=_run_action
    ):
        result = cap.run(no_wakeword=True, timeout=0.1, no_sound=False, max_turns=1)

    assert result["ok"] is True
    turn = result["turns"][0]
    assert turn["route"] == "local"
    assert turn["action"] == "remind.schedule"
    assert turn["slots"] == {"delay_sec": 10.0, "text": "喝水"}
    assert ("remind", {"delay_sec": 10.0, "text": "喝水"}) in calls
