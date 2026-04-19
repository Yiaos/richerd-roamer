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
}


def _extract_slots(text: str) -> dict[str, Any]:
    """Extract minimal slots from utterance (v1 best effort)."""
    slots: dict[str, Any] = {}

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
                slots=_extract_slots(normalized),
                text=normalized,
            )

    return success(
        matched=False,
        intent=None,
        action=None,
        slots=_extract_slots(normalized),
        text=normalized,
        reason="no_intent_match",
    )
