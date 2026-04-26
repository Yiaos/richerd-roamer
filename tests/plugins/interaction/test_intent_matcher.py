"""Tests for converse intent matcher service."""

from roamer.platform.contract import ErrorCode
from roamer.plugins.interaction.services.intent import match_intent

DEFAULT_INTENTS = [
    {"name": "time_now", "action": "time.now", "patterns": ["现在几点", "几点了"]},
    {"name": "status", "action": "sense", "patterns": ["你在哪", "状态"]},
    {"name": "watch", "action": "watch", "patterns": ["看一下", "拍张照"]},
    {"name": "go_home", "action": "motion.home", "patterns": ["回家", "回充电"]},
    {"name": "position", "action": "motion.position", "patterns": ["你在哪个位置", "当前位置"]},
]


def test_match_intent_hit_returns_action() -> None:
    result = match_intent("现在几点了", DEFAULT_INTENTS)
    assert result["ok"] is True
    assert result["matched"] is True
    assert result["intent"] == "time_now"
    assert result["action"] == "time.now"


def test_match_intent_miss_returns_fallback_shape() -> None:
    result = match_intent("给我讲个笑话", DEFAULT_INTENTS)
    assert result["ok"] is True
    assert result["matched"] is False
    assert result["intent"] is None
    assert result["action"] is None
    assert result["reason"] == "no_intent_match"


def test_match_intent_rejects_disallowed_action() -> None:
    bad = [{"name": "unsafe", "action": "shell.exec", "patterns": ["执行"]}]
    result = match_intent("执行 ls", bad)
    assert result["ok"] is False
    assert result["error_code"] == ErrorCode.CONVERSE_INTENT_INVALID_ACTION


def test_match_intent_extracts_basic_location_slot() -> None:
    result = match_intent("去客厅", DEFAULT_INTENTS)
    assert result["ok"] is True
    assert result["slots"].get("location") == "客厅"


def test_match_intent_extracts_chinese_spoken_reminder() -> None:
    result = match_intent("十秒后提醒我喝水", [])

    assert result["ok"] is True
    assert result["matched"] is True
    assert result["action"] == "remind.schedule"
    assert result["slots"] == {"delay_sec": 10.0, "text": "喝水"}


def test_match_intent_extracts_minute_reminder_with_default_text() -> None:
    result = match_intent("5分钟后提醒我", [])

    assert result["ok"] is True
    assert result["matched"] is True
    assert result["action"] == "remind.schedule"
    assert result["slots"] == {"delay_sec": 300.0, "text": "提醒"}
