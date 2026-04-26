"""Discord fallback sender for converse capability."""

from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any
from urllib import error as url_error
from urllib import request

from roamer.platform.contract import ErrorCode
from roamer.platform.output import error, success


def _utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _mention_prefix(discord_cfg: dict[str, Any]) -> str:
    """Return a Discord mention prefix for bot-to-bot fallback routing."""
    mention_user_id = str(discord_cfg.get("mention_user_id") or "").strip()
    mention_role_id = str(discord_cfg.get("mention_role_id") or "").strip()
    mention_raw = str(discord_cfg.get("mention") or "").strip()

    if mention_user_id:
        return f"<@{mention_user_id}> "
    if mention_role_id:
        return f"<@&{mention_role_id}> "
    if mention_raw:
        return mention_raw + " "
    return ""


def send_fallback(
    text: str,
    *,
    config: dict[str, Any],
    session_id: str,
    turn_id: int,
    timeout_sec: float = 3.0,
) -> dict[str, Any]:
    """Send fallback text to Discord channel using Bot REST API."""
    discord_cfg = (config or {}).get("discord", {})
    if not bool(discord_cfg.get("enabled", False)):
        return success(sent=False, skipped=True, reason="discord_disabled")

    channel_id = str(discord_cfg.get("channel_id") or "").strip()
    token_env = str(discord_cfg.get("token_env") or "DISCORD_BOT_TOKEN")
    token = os.getenv(token_env, "")
    source = str(discord_cfg.get("source") or "roamer")

    if not channel_id or not token:
        return error(
            "converse_discord_send_failed",
            "Discord fallback missing channel_id or token",
            error_code=ErrorCode.CONVERSE_DISCORD_SEND_FAILED,
            sent=False,
            skipped=True,
        )

    payload = {
        "source": source,
        "session_id": session_id,
        "turn_id": turn_id,
        "text": text,
        "timestamp": _utc_iso(),
    }

    instruction = (
        "请处理这条 Roamer 语音请求。回复给用户时，"
        "请同时通过 `ssh richerd@roamer 'roamer speak ...'` "
        "让 Roamer 语音播报你的最终回复。"
    )
    content = (
        _mention_prefix(discord_cfg)
        + "[roamer-fallback] "
        + instruction
        + "\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    body = {"content": content}

    req = request.Request(
        url=f"https://discord.com/api/v10/channels/{channel_id}/messages",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "roamer-converse/1.0",
        },
    )

    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            status = getattr(resp, "status", 200)
            if 200 <= status < 300:
                return success(sent=True, status=status, payload=payload, content=content)
            return error(
                "converse_discord_send_failed",
                f"Discord returned unexpected status: {status}",
                error_code=ErrorCode.CONVERSE_DISCORD_SEND_FAILED,
                sent=False,
                status=status,
            )
    except url_error.HTTPError as exc:
        return error(
            "converse_discord_send_failed",
            f"Discord HTTP error: {exc.code}",
            error_code=ErrorCode.CONVERSE_DISCORD_SEND_FAILED,
            sent=False,
            status=exc.code,
        )
    except Exception as exc:
        return error(
            "converse_discord_send_failed",
            f"Discord send failed: {exc}",
            error_code=ErrorCode.CONVERSE_DISCORD_SEND_FAILED,
            sent=False,
        )
