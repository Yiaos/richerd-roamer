"""Tests for SU-03T wake capability."""

from unittest.mock import Mock

from roamer.platform.contract import ErrorCode
from roamer.plugins.interaction.capabilities.wake import WakeCapability


def _config() -> dict:
    return {
        "converse": {
            "wakeword": {
                "enabled": True,
                "driver": "su03t_gpio",
                "phrases": ["richard", "rich erd", "瑞彻德"],
                "followup_timeout_sec": 10.0,
            },
            "endpoint": {"max_record_sec": 8.0},
            "intents": [{"name": "time_now", "action": "time.now", "patterns": ["几点"]}],
            "discord": {"enabled": False, "channel_id": "", "token_env": "DISCORD_BOT_TOKEN"},
        }
    }


def test_wake_once_routes_stripped_command() -> None:
    cap = WakeCapability(_config())
    cap._wait_for_trigger = Mock(return_value=True)
    cap._listen_once = Mock(return_value={"ok": True, "text": "Richard 现在几点了"})
    cap._route_text = Mock(return_value={"turn_id": 1, "route": "local"})

    result = cap.run(once=True, timeout=1.0, no_sound=True)

    assert result["ok"] is True
    cap._route_text.assert_called_once()
    assert cap._route_text.call_args.kwargs["text"] == "现在几点了"


def test_wake_once_waits_for_valid_wake_phrase_after_non_match() -> None:
    config = _config()
    config["converse"]["wakeword"]["min_interval_sec"] = 0
    cap = WakeCapability(config)
    cap._wait_for_trigger = Mock(return_value=True)
    cap._listen_once = Mock(
        side_effect=[
            {"ok": True, "text": "现在几点了"},
            {"ok": True, "text": "Richard 现在几点了"},
        ]
    )
    cap._route_text = Mock(return_value={"turn_id": 1, "route": "local"})

    result = cap.run(once=True, timeout=1.0, no_sound=True)

    assert result["ok"] is True
    assert "ignored" not in result
    assert cap._listen_once.call_count == 2
    cap._route_text.assert_called_once()
    assert cap._route_text.call_args.kwargs["text"] == "现在几点了"


def test_wake_service_mode_keeps_polling_after_empty_timeout() -> None:
    cap = WakeCapability(_config())
    cap._wait_for_trigger = Mock(side_effect=[False, True])
    cap._listen_once = Mock(return_value={"ok": True, "text": "Richard 现在几点了"})
    cap._route_text = Mock(
        return_value={
            "ok": False,
            "intent_result": {
                "ok": False,
                "error": "converse_intent_invalid_action",
                "message": "invalid action",
                "error_code": "converse.intent.invalid_action",
            },
        }
    )

    result = cap.run(once=False, timeout=None, no_sound=True)

    assert result["ok"] is False
    assert cap._wait_for_trigger.call_count == 2


def test_wake_throttles_repeated_triggers_at_capability_level() -> None:
    now = [100.0]
    cap = WakeCapability(_config(), clock=lambda: now[0])

    assert cap._accept_trigger() is True
    now[0] = 100.5
    assert cap._accept_trigger() is False
    now[0] = 102.0
    assert cap._accept_trigger() is True


def test_wake_trigger_failure_returns_canonical_error() -> None:
    cap = WakeCapability(_config())
    cap._start_preroll_source_if_needed = Mock(return_value=None)
    cap._wait_for_trigger = Mock(side_effect=RuntimeError("gpio unavailable"))

    result = cap.run(once=True, timeout=1.0, no_sound=True)

    assert result["ok"] is False
    assert result["error_code"] == ErrorCode.CONVERSE_WAKEWORD_UNAVAILABLE


def test_wake_preroll_start_failure_returns_structured_audio_error() -> None:
    cap = WakeCapability(_config())
    cap._start_preroll_source_if_needed = Mock(side_effect=FileNotFoundError("arecord"))

    result = cap.run(once=True, timeout=1.0, no_sound=True)

    assert result["ok"] is False
    assert result["error_code"] == ErrorCode.DEPENDENCY_AUDIO_ARECORD_MISSING


def test_wake_clears_preroll_after_routing_before_followup() -> None:
    pre_roll = Mock()
    cap = WakeCapability(_config())
    cap._wait_for_trigger = Mock(return_value=True)
    cap._start_preroll_source_if_needed = Mock(return_value=pre_roll)
    cap._listen_once = Mock(return_value={"ok": True, "text": "Richard 现在几点了"})
    cap._route_text = Mock(return_value={"turn_id": 1, "route": "local"})

    result = cap.run(once=True, timeout=1.0, no_sound=False)

    assert result["ok"] is True
    pre_roll.clear.assert_called_once()


def test_wake_once_waits_for_followup_command_after_wake_phrase_only() -> None:
    config = _config()
    config["converse"]["wakeword"]["min_interval_sec"] = 0
    cap = WakeCapability(config)
    cap._wait_for_trigger = Mock(return_value=True)
    cap._listen_once = Mock(
        side_effect=[
            {"ok": True, "text": "Richard"},
            {"ok": True, "text": "现在几点了"},
        ]
    )
    cap._route_text = Mock(return_value={"turn_id": 2, "route": "local"})

    result = cap.run(once=True, timeout=1.0, no_sound=True)

    assert result["ok"] is True
    assert "followup" not in result
    assert cap._listen_once.call_count == 2
    cap._route_text.assert_called_once()
    assert cap._route_text.call_args.kwargs["text"] == "现在几点了"
    assert cap._route_text.call_args.kwargs["allow_fallback"] is False


def test_wake_treats_repeated_wake_phrase_as_wake_only() -> None:
    config = _config()
    config["converse"]["wakeword"]["min_interval_sec"] = 0
    cap = WakeCapability(config)
    cap._wait_for_trigger = Mock(return_value=True)
    cap._listen_once = Mock(
        side_effect=[
            {"ok": True, "text": "richard richard"},
            {"ok": True, "text": "现在几点了"},
        ]
    )
    cap._route_text = Mock(return_value={"turn_id": 1, "route": "local"})

    result = cap.run(once=True, timeout=1.0, no_sound=True)

    assert result["ok"] is True
    cap._route_text.assert_called_once()
    assert cap._route_text.call_args.kwargs["text"] == "现在几点了"
    assert cap._route_text.call_args.kwargs["allow_fallback"] is False


def test_wake_followup_unmatched_text_does_not_refresh_followup() -> None:
    now = [100.0]
    config = _config()
    config["converse"]["wakeword"]["min_interval_sec"] = 0
    config["converse"]["wakeword"]["followup_timeout_sec"] = 10.0
    cap = WakeCapability(config, clock=lambda: now[0])
    cap._wait_for_trigger = Mock(return_value=True)
    cap._listen_once = Mock(
        side_effect=[
            {"ok": True, "text": "Richard"},
            {"ok": True, "text": "嗯"},
        ]
    )
    cap._route_text = Mock(return_value={"turn_id": 1, "route": "ignored"})

    result = cap.run(once=True, timeout=1.0, no_sound=True)

    assert result["ok"] is True
    cap._route_text.assert_called_once()
    assert cap._route_text.call_args.kwargs["text"] == "嗯"
    assert cap._route_text.call_args.kwargs["allow_fallback"] is False
    assert cap._followup_until == 110.0


def test_wake_once_propagates_route_text_failure() -> None:
    cap = WakeCapability(_config())
    cap._wait_for_trigger = Mock(return_value=True)
    cap._listen_once = Mock(return_value={"ok": True, "text": "Richard 现在几点了"})
    cap._route_text = Mock(
        return_value={
            "ok": False,
            "intent_result": {
                "ok": False,
                "error": "converse_intent_invalid_action",
                "message": "invalid action",
                "error_code": "converse.intent.invalid_action",
            },
        }
    )

    result = cap.run(once=True, timeout=1.0, no_sound=True)

    assert result["ok"] is False
    assert result["error_code"] == "converse.intent.invalid_action"


def test_wake_service_mode_does_not_accumulate_turns_forever() -> None:
    config = _config()
    config["converse"]["wakeword"]["min_interval_sec"] = 0
    cap = WakeCapability(config)
    cap._wait_for_trigger = Mock(return_value=True)
    cap._listen_once = Mock(
        side_effect=[
            {"ok": True, "text": "noise"},
            {"ok": True, "text": "noise again"},
            {"ok": True, "text": "Richard 现在几点了"},
        ]
    )
    cap._route_text = Mock(
        return_value={
            "ok": False,
            "intent_result": {
                "ok": False,
                "error": "converse_intent_invalid_action",
                "message": "invalid action",
                "error_code": "converse.intent.invalid_action",
            },
        }
    )

    result = cap.run(once=False, timeout=1.0, no_sound=True)

    assert result["ok"] is False
    assert "turns" not in result
    assert cap._listen_once.call_count == 3
