"""Wake phrase matching for hands-free converse."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass


_LEADING_JUNK_RE = re.compile(r"^[\s,，。.!！?？:：;；、\"'“”‘’\-_]+")
_SEPARATOR_RE = re.compile(r"[\s\-_]+")


@dataclass(frozen=True)
class WakeMatch:
    """Result of matching a wake phrase at the start of ASR text."""

    matched: bool
    phrase: str | None
    command_text: str


def _canonical_ascii(text: str) -> str:
    return _SEPARATOR_RE.sub("", text.casefold())


def _strip_prefix(original: str, length: int) -> str:
    return _LEADING_JUNK_RE.sub("", original[length:]).strip()


def match_wake_phrase(text: str, phrases: Sequence[str]) -> WakeMatch:
    """Match a configured wake phrase at the beginning of ASR text."""
    original = str(text or "")
    stripped = _LEADING_JUNK_RE.sub("", original).strip()
    folded = stripped.casefold()
    compact = _canonical_ascii(stripped)

    for phrase in phrases:
        phrase_text = str(phrase or "").strip()
        if not phrase_text:
            continue

        phrase_folded = phrase_text.casefold()
        phrase_compact = _canonical_ascii(phrase_text)

        if phrase_text[0].isascii():
            if compact.startswith(phrase_compact):
                consumed = _ascii_consumed_length(stripped, phrase_compact)
                return WakeMatch(True, phrase_text, _strip_prefix(stripped, consumed))
            continue

        if folded.startswith(phrase_folded):
            return WakeMatch(True, phrase_text, _strip_prefix(stripped, len(phrase_text)))

    return WakeMatch(False, None, original.strip())


def _ascii_consumed_length(text: str, compact_phrase: str) -> int:
    seen = ""
    for index, char in enumerate(text):
        if _SEPARATOR_RE.fullmatch(char):
            continue
        seen += char.casefold()
        if seen == compact_phrase:
            return index + 1
    return 0
