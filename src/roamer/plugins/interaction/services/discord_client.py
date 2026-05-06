"""Discord fallback sender for converse capability."""

from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any
from urllib import error as url_error
from urllib import request

from roamer.platform.contract import ErrorCode
from roamer.platform.logging import log_event
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


def _read_response_json(resp: Any) -> dict[str, Any]:
    read = getattr(resp, "read", None)
    if not callable(read):
        return {}
    try:
        raw = read()
        if not raw:
            return {}
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


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
    logging_cfg = (config or {}).get("logging", {})
    if not bool(discord_cfg.get("enabled", False)):
        result = success(sent=False, skipped=True, reason="discord_disabled")
        log_event(
            "discord",
            "send_result",
            ok=True,
            sent=False,
            skipped=True,
            reason="discord_disabled",
            session_id=session_id,
            turn_id=turn_id,
        )
        return result

    channel_id = str(discord_cfg.get("channel_id") or "").strip()
    token_env = str(discord_cfg.get("token_env") or "DISCORD_BOT_TOKEN")
    token = os.getenv(token_env, "")
    source = str(discord_cfg.get("source") or "roamer")

    if not channel_id or not token:
        result = error(
            "converse_discord_send_failed",
            "Discord fallback missing channel_id or token",
            error_code=ErrorCode.CONVERSE_DISCORD_SEND_FAILED,
            sent=False,
            skipped=True,
        )
        log_event(
            "discord",
            "send_result",
            ok=False,
            sent=False,
            skipped=True,
            error_code=result.get("error_code"),
            reason="missing_channel_or_token",
            channel_configured=bool(channel_id),
            token_env=token_env,
            token_configured=bool(token),
            session_id=session_id,
            turn_id=turn_id,
        )
        return result

    payload = {
        "source": source,
        "session_id": session_id,
        "turn_id": turn_id,
        "text": text,
        "timestamp": _utc_iso(),
    }

    instruction = str(
        discord_cfg.get("reply_instruction")
        or "通过 roamer control node 语音播报回复"
    )
    mention_prefix = _mention_prefix(discord_cfg)
    content = mention_prefix + str(text).strip() + "\n" + instruction
    body = {"content": content}
    log_transcripts = bool(logging_cfg.get("log_transcripts", True))
    log_event(
        "discord",
        "send_request",
        channel_id=channel_id,
        session_id=session_id,
        turn_id=turn_id,
        content=content if log_transcripts else "",
        content_length=len(content),
        mention_configured=bool(mention_prefix),
        timeout_sec=timeout_sec,
    )

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
            response_payload = _read_response_json(resp)
            if 200 <= status < 300:
                result = success(sent=True, status=status, payload=payload, content=content)
                log_event(
                    "discord",
                    "send_result",
                    ok=True,
                    sent=True,
                    status=status,
                    status_code=status,
                    message_id=response_payload.get("id"),
                    session_id=session_id,
                    turn_id=turn_id,
                )
                return result
            result = error(
                "converse_discord_send_failed",
                f"Discord returned unexpected status: {status}",
                error_code=ErrorCode.CONVERSE_DISCORD_SEND_FAILED,
                sent=False,
                status=status,
            )
            log_event(
                "discord",
                "send_result",
                ok=False,
                sent=False,
                status=status,
                status_code=status,
                error_code=result.get("error_code"),
                session_id=session_id,
                turn_id=turn_id,
            )
            return result
    except url_error.HTTPError as exc:
        result = error(
            "converse_discord_send_failed",
            f"Discord HTTP error: {exc.code}",
            error_code=ErrorCode.CONVERSE_DISCORD_SEND_FAILED,
            sent=False,
            status=exc.code,
        )
        log_event(
            "discord",
            "send_result",
            ok=False,
            sent=False,
            status=exc.code,
            status_code=exc.code,
            error_code=result.get("error_code"),
            session_id=session_id,
            turn_id=turn_id,
        )
        return result
    except Exception as exc:
        result = error(
            "converse_discord_send_failed",
            f"Discord send failed: {exc}",
            error_code=ErrorCode.CONVERSE_DISCORD_SEND_FAILED,
            sent=False,
        )
        log_event(
            "discord",
            "send_result",
            ok=False,
            sent=False,
            error_code=result.get("error_code"),
            error_type=type(exc).__name__,
            error_message=str(exc),
            session_id=session_id,
            turn_id=turn_id,
        )
        return result
