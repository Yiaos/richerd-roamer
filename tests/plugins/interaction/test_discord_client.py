"""Tests for converse Discord fallback client."""

import io
import json
from unittest.mock import patch
from urllib.error import HTTPError

from roamer.platform.contract import ErrorCode
from roamer.plugins.interaction.services.discord_client import send_fallback


def _cfg(enabled: bool = True) -> dict:
    return {
        "discord": {
            "enabled": enabled,
            "channel_id": "123456",
            "token_env": "DISCORD_BOT_TOKEN",
            "source": "roamer",
        }
    }


def test_send_fallback_success() -> None:
    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    with patch("os.getenv", return_value="token"):
        with patch("urllib.request.urlopen", return_value=_Resp()):
            result = send_fallback(
                "hello",
                config=_cfg(),
                session_id="s1",
                turn_id=1,
            )

    assert result["ok"] is True
    assert result["sent"] is True
    assert result["payload"]["source"] == "roamer"
    assert result["payload"]["session_id"] == "s1"
    assert result["payload"]["turn_id"] == 1
    assert result["payload"]["text"] == "hello"
    assert "timestamp" in result["payload"]


def test_send_fallback_http_error() -> None:
    with patch("os.getenv", return_value="token"):
        with patch(
            "urllib.request.urlopen",
            side_effect=HTTPError("u", 500, "err", hdrs=None, fp=io.BytesIO(b"")),
        ):
            result = send_fallback("x", config=_cfg(), session_id="s1", turn_id=2)

    assert result["ok"] is False
    assert result["error_code"] == ErrorCode.CONVERSE_DISCORD_SEND_FAILED


def test_send_fallback_timeout_or_runtime_error() -> None:
    with patch("os.getenv", return_value="token"):
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timeout")):
            result = send_fallback("x", config=_cfg(), session_id="s1", turn_id=3)

    assert result["ok"] is False
    assert result["error_code"] == ErrorCode.CONVERSE_DISCORD_SEND_FAILED


def test_send_fallback_disabled() -> None:
    result = send_fallback("x", config=_cfg(enabled=False), session_id="s1", turn_id=4)
    assert result["ok"] is True
    assert result["sent"] is False
    assert result["skipped"] is True
