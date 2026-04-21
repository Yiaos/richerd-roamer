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

    with patch("roamer.plugins.interaction.capabilities.converse.run_action", side_effect=_run_action):
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

    with patch("roamer.plugins.interaction.capabilities.converse.run_action", side_effect=_run_action):
        with patch(
            "roamer.plugins.interaction.capabilities.converse.send_fallback",
            return_value={"ok": True, "sent": False, "skipped": True},
        ):
            result = cap.run(no_wakeword=True, timeout=0.1, no_sound=True, max_turns=2)

    assert result["ok"] is True
    assert result["turns"][0]["route"] == "discord"


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

    with patch("roamer.plugins.interaction.capabilities.converse.get_driver", side_effect=RuntimeError("no driver")):
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

    with patch("roamer.plugins.interaction.capabilities.converse.get_driver", return_value=_Driver()):
        result = cap.run(no_wakeword=False, timeout=0.1, no_sound=True, max_turns=1)

    assert result["ok"] is True
    assert result["reason"] == "wakeword_timeout"
    assert result["turns"] == []
