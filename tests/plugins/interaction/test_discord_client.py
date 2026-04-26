"""Tests for converse Discord fallback client."""

import io
import json
from unittest.mock import patch
from urllib.error import HTTPError

from roamer.platform.contract import ErrorCode
from roamer.plugins.interaction.services.discord_client import send_fallback


def _cfg(enabled: bool = True, **discord_overrides) -> dict:
    discord = {
        "enabled": enabled,
        "channel_id": "123456",
        "token_env": "DISCORD_BOT_TOKEN",
        "source": "roamer",
    }
    discord.update(discord_overrides)
    return {"discord": discord}


class _Resp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_send_fallback_success() -> None:
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
    assert result["content"].startswith("[roamer-fallback] ")
    assert "roamer speak" in result["content"]
    assert "timestamp" in result["payload"]


def test_send_fallback_prefixes_user_mention() -> None:
    captured = {}

    def _urlopen(req, timeout):
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _Resp()

    with patch("os.getenv", return_value="token"):
        with patch("urllib.request.urlopen", side_effect=_urlopen):
            result = send_fallback(
                "help",
                config=_cfg(mention_user_id="1477701379437891695"),
                session_id="s1",
                turn_id=2,
            )

    assert result["ok"] is True
    assert result["content"].startswith("<@1477701379437891695> [roamer-fallback] ")
    assert captured["body"]["content"] == result["content"]


def test_send_fallback_prefixes_role_mention_when_no_user() -> None:
    with patch("os.getenv", return_value="token"):
        with patch("urllib.request.urlopen", return_value=_Resp()):
            result = send_fallback(
                "help",
                config=_cfg(mention_role_id="42"),
                session_id="s1",
                turn_id=2,
            )

    assert result["ok"] is True
    assert result["content"].startswith("<@&42> [roamer-fallback] ")


def test_send_fallback_prefixes_raw_mention_when_configured() -> None:
    with patch("os.getenv", return_value="token"):
        with patch("urllib.request.urlopen", return_value=_Resp()):
            result = send_fallback(
                "help",
                config=_cfg(mention="@Richerd"),
                session_id="s1",
                turn_id=2,
            )

    assert result["ok"] is True
    assert result["content"].startswith("@Richerd [roamer-fallback] ")


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
