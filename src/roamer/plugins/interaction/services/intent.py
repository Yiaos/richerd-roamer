"""Intent matching service for converse capability."""

from __future__ import annotations

import re
from typing import Any

from roamer.platform.contract import ErrorCode
from roamer.platform.output import error, success

ALLOWED_INTENT_ACTIONS = {
    "time.now",
    "sense",
    "watch",
    "motion.home",
    "motion.position",
    "remind.schedule",
}

_CN_NUMERAL = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def _parse_cn_number(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    if value == "十":
        return 10
    if value.startswith("十") and len(value) == 2:
        ones = _CN_NUMERAL.get(value[1])
        return 10 + ones if ones is not None else None
    if value.endswith("十") and len(value) == 2:
        tens = _CN_NUMERAL.get(value[0])
        return tens * 10 if tens is not None else None
    if "十" in value and len(value) == 3:
        tens = _CN_NUMERAL.get(value[0])
        ones = _CN_NUMERAL.get(value[2])
        if tens is not None and ones is not None:
            return tens * 10 + ones
    return _CN_NUMERAL.get(value)


def _extract_reminder_slots(text: str) -> dict[str, Any] | None:
    pattern = re.compile(
        r"(?P<amount>\d+(?:\.\d+)?|[零一二两三四五六七八九十]{1,3})"
        r"(?P<unit>秒|分钟|分|小时|时|s|sec|secs|second|seconds|m|min|mins|"
        r"minute|minutes|h|hr|hour|hours)"
        r"后(?:提醒我|提醒)?(?P<message>.*)"
    )
    match = pattern.search(text)
    if not match:
        return None

    amount_raw = match.group("amount")
    if re.fullmatch(r"\d+(?:\.\d+)?", amount_raw):
        amount = float(amount_raw)
    else:
        amount = _parse_cn_number(amount_raw)
    if amount is None:
        return None

    unit = match.group("unit")
    multiplier = 1
    if unit in {"分钟", "分", "m", "min", "mins", "minute", "minutes"}:
        multiplier = 60
    elif unit in {"小时", "时", "h", "hr", "hour", "hours"}:
        multiplier = 3600

    message = match.group("message").strip(" ，。,.！!") or "提醒"
    return {"delay_sec": float(amount) * multiplier, "text": message}


def _extract_slots(text: str) -> dict[str, Any]:
    """Extract minimal slots from utterance (v1 best effort)."""
    slots: dict[str, Any] = {}

    reminder = _extract_reminder_slots(text)
    if reminder:
        slots.update(reminder)

    # Example: "去客厅" -> {"location": "客厅"}
    match = re.search(r"去([\u4e00-\u9fa5A-Za-z0-9_-]{1,20})", text)
    if match:
        slots["location"] = match.group(1)

    return slots


def match_intent(text: str, intents: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Match text against configured intents.

    Returns success payload for both matched and unmatched cases.
    Returns error payload only when config is unsafe (invalid action).
    """
    normalized = (text or "").strip()
    if not normalized:
        return success(matched=False, intent=None, action=None, slots={}, reason="empty_text")

    slots = _extract_slots(normalized)
    if "delay_sec" in slots:
        return success(
            matched=True,
            intent="reminder",
            action="remind.schedule",
            slots=slots,
            text=normalized,
        )

    for intent in intents or []:
        name = str(intent.get("name") or "")
        action = str(intent.get("action") or "")
        patterns = [str(p) for p in intent.get("patterns", [])]

        if action and action not in ALLOWED_INTENT_ACTIONS:
            return error(
                "converse_intent_invalid_action",
                f"Intent '{name or '<unnamed>'}' uses disallowed action: {action}",
                error_code=ErrorCode.CONVERSE_INTENT_INVALID_ACTION,
                intent=name,
                action=action,
            )

        if any(pattern and pattern in normalized for pattern in patterns):
            return success(
                matched=True,
                intent=name,
                action=action,
                slots=slots,
                text=normalized,
            )

    return success(
        matched=False,
        intent=None,
        action=None,
        slots=slots,
        text=normalized,
        reason="no_intent_match",
    )
