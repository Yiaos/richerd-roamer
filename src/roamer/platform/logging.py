"""Structured runtime logging for Roamer services."""

from __future__ import annotations

import json
import logging as py_logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

_LOGGER_NAME = "roamer"
_SENSITIVE_KEY_PARTS = ("token", "secret", "password", "authorization", "proxy")
_CLEANUP_INTERVAL_SEC = 60 * 60
_ACTIVE_LOG_DIR: Path | None = None
_ACTIVE_RETENTION_DAYS = 3
_NEXT_CLEANUP_AT = 0.0
_LOG_TRANSCRIPTS = True
_REQUEST_ID: ContextVar[str | None] = ContextVar("roamer_request_id", default=None)


class _JsonLineFormatter(py_logging.Formatter):
    def format(self, record: py_logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "level": record.levelname,
            **getattr(record, "payload", {}),
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def mask_sensitive_value(value: str) -> str:
    """Mask a sensitive value while preserving enough edge characters for debugging."""
    text = str(value)
    if len(text) <= 2:
        return "***"
    if len(text) <= 8:
        return f"{text[0]}***{text[-1]}"
    return f"{text[:4]}***{text[-4:]}"


def _mask_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return mask_sensitive_value(value)

    if not parsed.scheme or not parsed.netloc or "@" not in parsed.netloc:
        return mask_sensitive_value(value)

    userinfo, hostinfo = parsed.netloc.rsplit("@", 1)
    if ":" in userinfo:
        user, password = userinfo.split(":", 1)
        masked_userinfo = f"{mask_sensitive_value(user)}:{mask_sensitive_value(password)}"
    else:
        masked_userinfo = mask_sensitive_value(userinfo)
    return urlunsplit(
        SplitResult(
            parsed.scheme,
            f"{masked_userinfo}@{hostinfo}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def redact_sensitive(data: Any, *, key: str = "") -> Any:
    """Recursively redact sensitive fields from log payloads."""
    if isinstance(data, dict):
        return {str(k): redact_sensitive(v, key=str(k)) for k, v in data.items()}
    if isinstance(data, list):
        return [redact_sensitive(item, key=key) for item in data]
    if isinstance(data, tuple):
        return [redact_sensitive(item, key=key) for item in data]
    if _is_sensitive_key(key):
        text = str(data)
        if "://" in text:
            return _mask_url(text)
        return mask_sensitive_value(text)
    return data


def setup_logging(config: dict[str, Any]) -> None:
    """Configure Roamer JSONL file logging from config."""
    global _ACTIVE_LOG_DIR, _ACTIVE_RETENTION_DAYS, _LOG_TRANSCRIPTS, _NEXT_CLEANUP_AT

    logging_cfg = config.get("logging", {})
    _LOG_TRANSCRIPTS = bool(logging_cfg.get("log_transcripts", True))
    logger = py_logging.getLogger(_LOGGER_NAME)
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)

    if not bool(logging_cfg.get("enabled", True)):
        _ACTIVE_LOG_DIR = None
        logger.addHandler(py_logging.NullHandler())
        logger.propagate = False
        return

    try:
        log_dir = Path(str(logging_cfg.get("dir", "/var/log/roamer"))).expanduser()
        retention_days = int(logging_cfg.get("retention_days", 3))
        log_dir.mkdir(parents=True, exist_ok=True)
        _cleanup_old_logs(log_dir, retention_days=retention_days)
        _ACTIVE_LOG_DIR = log_dir
        _ACTIVE_RETENTION_DAYS = retention_days
        _NEXT_CLEANUP_AT = time.time() + _CLEANUP_INTERVAL_SEC
        handler = RotatingFileHandler(
            log_dir / "roamer.log",
            maxBytes=int(logging_cfg.get("max_bytes", 10 * 1024 * 1024)),
            backupCount=int(logging_cfg.get("backup_count", 10)),
            encoding="utf-8",
        )
    except OSError:
        _ACTIVE_LOG_DIR = None
        handler = py_logging.NullHandler()
    handler.setFormatter(_JsonLineFormatter())

    logger.addHandler(handler)
    logger.setLevel(str(logging_cfg.get("level", "INFO")).upper())
    logger.propagate = False


def current_request_id() -> str | None:
    """Return the active request id for the current execution context."""
    return _REQUEST_ID.get()


def log_transcripts_enabled() -> bool:
    """Return whether logs may include full transcript/content text."""
    return _LOG_TRANSCRIPTS


@contextmanager
def request_context(request_id: str) -> Iterator[None]:
    """Attach a request id to all log events emitted in this context."""
    token = _REQUEST_ID.set(str(request_id))
    try:
        yield
    finally:
        _REQUEST_ID.reset(token)


def log_event(component: str, event: str, *, level: str = "INFO", **fields: Any) -> None:
    """Write one structured runtime event if logging has been configured."""
    logger = py_logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        return
    _maybe_cleanup_old_logs()
    request_id = current_request_id()
    if request_id and "request_id" not in fields:
        fields = {"request_id": request_id, **fields}
    payload = {
        "component": component,
        "event": event,
        **redact_sensitive(fields),
    }
    logger.log(getattr(py_logging, level.upper(), py_logging.INFO), "", extra={"payload": payload})


def _cleanup_old_logs(log_dir: Path, *, retention_days: int) -> None:
    if retention_days <= 0:
        return
    cutoff = time.time() - (retention_days * 24 * 60 * 60)
    for path in log_dir.glob("roamer.log*"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
        except FileNotFoundError:
            continue


def _maybe_cleanup_old_logs() -> None:
    global _NEXT_CLEANUP_AT

    if _ACTIVE_LOG_DIR is None:
        return
    now = time.time()
    if now < _NEXT_CLEANUP_AT:
        return
    _cleanup_old_logs(_ACTIVE_LOG_DIR, retention_days=_ACTIVE_RETENTION_DAYS)
    _NEXT_CLEANUP_AT = now + _CLEANUP_INTERVAL_SEC
