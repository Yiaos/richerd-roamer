"""Privacy and redaction helpers."""

from __future__ import annotations

from roamerd.events.base import JSONDict, JSONValue

SENSITIVE_KEYS = {"token", "password", "secret", "api_key", "authorization"}


def redact_payload(
    payload: JSONDict,
    *,
    log_transcripts: bool,
    log_audio_paths: bool,
) -> tuple[JSONDict, bool]:
    redacted = False
    clean: JSONDict = {}
    for key, value in payload.items():
        lowered = key.lower()
        if lowered in SENSITIVE_KEYS or lowered.endswith("_token"):
            clean[key] = "[REDACTED]"
            redacted = True
        elif lowered in {"text", "transcript", "command_text"} and not log_transcripts:
            text = str(value) if value is not None else ""
            clean[key] = f"[REDACTED len={len(text)}]"
            redacted = True
        elif lowered in {"audio_path", "path"} and "audio" in lowered and not log_audio_paths:
            clean[key] = "[REDACTED]"
            redacted = True
        elif isinstance(value, dict):
            nested, nested_redacted = redact_payload(
                value,
                log_transcripts=log_transcripts,
                log_audio_paths=log_audio_paths,
            )
            clean[key] = nested
            redacted = redacted or nested_redacted
        else:
            clean[key] = value
    return clean, redacted


def json_safe_summary(value: JSONValue) -> JSONValue:
    return value
