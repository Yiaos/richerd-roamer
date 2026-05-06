"""Tests for SU-03T wake phrase text matching."""

from roamer.plugins.interaction.services.wake_phrases import match_wake_phrase

PHRASES = ["richard", "rich erd", "瑞彻德"]


def test_matches_english_prefix_and_strips_command() -> None:
    result = match_wake_phrase("Richard 现在几点了", PHRASES)

    assert result.matched is True
    assert result.phrase == "richard"
    assert result.command_text == "现在几点了"


def test_matches_hyphenated_variant() -> None:
    result = match_wake_phrase("rich-erd 回家", PHRASES)

    assert result.matched is True
    assert result.phrase == "rich erd"
    assert result.command_text == "回家"


def test_matches_chinese_variant() -> None:
    result = match_wake_phrase("瑞彻德 看一下", PHRASES)

    assert result.matched is True
    assert result.phrase == "瑞彻德"
    assert result.command_text == "看一下"


def test_non_prefix_does_not_match() -> None:
    result = match_wake_phrase("现在几点了 Richard", PHRASES)

    assert result.matched is False
    assert result.command_text == "现在几点了 Richard"


def test_wake_phrase_only_returns_empty_command() -> None:
    result = match_wake_phrase(" Richard ", PHRASES)

    assert result.matched is True
    assert result.command_text == ""
