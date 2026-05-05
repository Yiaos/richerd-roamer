"""Tests for SU-03T wake capability."""

from unittest.mock import Mock

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


def test_wake_once_ignores_non_wake_text() -> None:
    cap = WakeCapability(_config())
    cap._wait_for_trigger = Mock(return_value=True)
    cap._listen_once = Mock(return_value={"ok": True, "text": "现在几点了"})

    result = cap.run(once=True, timeout=1.0, no_sound=True)

    assert result["ok"] is True
    assert result["ignored"] is True
    assert result["reason"] == "wake_phrase_not_matched"


def test_wake_followup_routes_without_wake_phrase() -> None:
    cap = WakeCapability(_config())
    cap._wait_for_trigger = Mock(return_value=True)
    cap._listen_once = Mock(return_value={"ok": True, "text": "Richard"})
    cap._route_text = Mock(return_value={"turn_id": 2, "route": "local"})

    first = cap.run(once=True, timeout=1.0, no_sound=True)
    assert first["followup"] is True

    cap._listen_once = Mock(return_value={"ok": True, "text": "现在几点了"})
    second = cap.run(once=True, timeout=1.0, no_sound=True)

    assert second["ok"] is True
    cap._route_text.assert_called_once()
    assert cap._route_text.call_args.kwargs["text"] == "现在几点了"
