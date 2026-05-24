from __future__ import annotations


def strip_wake_phrase(text: str, phrases: list[str]) -> str:
    clean = text.strip()
    for phrase in sorted(phrases, key=len, reverse=True):
        if not clean.startswith(phrase):
            continue
        clean = clean[len(phrase) :].lstrip(" ，,。.!！?？")
        break
    return clean.strip()
