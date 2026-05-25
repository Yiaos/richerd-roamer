from __future__ import annotations

import contextlib
import contextvars
import json
import time
from collections import deque
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from pydantic import BaseModel, ConfigDict

from roamerd.events import Event
from roamerd.kernel.event_bus import EventBus
from roamerd.types import JSONDict, JSONValue

_turn_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("turn_id", default=None)
_action_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("action_id", default=None)
_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)


class TraceLoggerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    log_dir: Path
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 10
    retention_days: int = 3
    log_transcripts: bool = True
    log_audio_paths: bool = False
    seen_event_id_limit: int = 10_000
    stale_action_after_sec: float = 60 * 60


class TraceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: str
    level: str
    event_type: str
    session_id: str
    turn_id: str | None = None
    action_id: str | None = None
    correlation_id: str | None = None
    request_id: str | None = None
    source: str = ""
    payload: JSONDict
    redacted: bool = False


class TraceLogger:
    def __init__(self, config: TraceLoggerConfig, *, session_id: str) -> None:
        self._config = config
        self._session_id = session_id
        self._config.log_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_retention()
        self._file_index = 0
        self._file = self._open_file()
        self._action_started_at: dict[str, datetime] = {}
        self._seen_event_ids: set[str] = set()
        self._seen_event_ids_order: deque[str] = deque()

    async def start(self, bus: EventBus) -> None:
        bus.subscribe_pattern("*", self._handle_event)

    @contextlib.contextmanager
    def bind_turn(self, turn_id: str) -> Iterator[None]:
        token = _turn_id.set(turn_id)
        try:
            yield
        finally:
            _turn_id.reset(token)

    @contextlib.contextmanager
    def bind_action(self, action_id: str) -> Iterator[None]:
        token = _action_id.set(action_id)
        try:
            yield
        finally:
            _action_id.reset(token)

    @contextlib.contextmanager
    def bind_correlation(self, correlation_id: str) -> Iterator[None]:
        token = _correlation_id.set(correlation_id)
        try:
            yield
        finally:
            _correlation_id.reset(token)

    def log(
        self,
        event_type: str,
        payload: JSONDict,
        *,
        level: str = "info",
        source: str = "",
        turn_id: str | None = None,
        action_id: str | None = None,
        correlation_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        redacted_payload, redacted = self._redact(payload)
        entry = TraceEntry(
            timestamp=datetime.now(UTC).isoformat(),
            level=level,
            event_type=event_type,
            session_id=self._session_id,
            turn_id=turn_id or _turn_id.get(),
            action_id=action_id or _action_id.get(),
            correlation_id=correlation_id or _correlation_id.get(),
            request_id=request_id,
            source=source,
            payload=redacted_payload,
            redacted=redacted,
        )
        self._write_entry(entry)
        if level == "error" or event_type.startswith("safety."):
            self._file.flush()

    def log_action_start(self, action_id: str, *, action_type: str, resource: str) -> None:
        self._cleanup_stale_action_starts()
        self._action_started_at[action_id] = datetime.now(UTC)
        self.log(
            "action.started",
            {"action_type": action_type, "resource": resource},
            source="action_manager",
            action_id=action_id,
        )

    def log_action_end(self, action_id: str, result: JSONDict) -> None:
        self._cleanup_stale_action_starts()
        started = self._action_started_at.pop(action_id, None)
        duration_ms = 0.0
        if started is not None:
            duration_ms = (datetime.now(UTC) - started).total_seconds() * 1000
        payload = dict(result)
        payload["duration_ms"] = duration_ms
        self.log(
            "action.completed",
            payload,
            source="action_manager",
            action_id=action_id,
        )

    def close(self) -> None:
        self._file.flush()
        self._file.close()

    def flush(self) -> None:
        self._file.flush()

    @property
    def log_dir(self) -> Path:
        return self._config.log_dir

    async def _handle_event(self, event: Event) -> None:
        if event.event_id in self._seen_event_ids:
            return
        self._remember_event_id(event.event_id)
        self.log(
            event.event_type,
            event.payload,
            source=event.source,
            turn_id=event.turn_id,
            action_id=event.action_id,
            correlation_id=event.correlation_id,
            level="error" if event.priority.value == "critical" else "info",
        )

    def _write_entry(self, entry: TraceEntry) -> None:
        line = json.dumps(entry.model_dump(exclude_none=True), ensure_ascii=False) + "\n"
        if self._file.tell() + len(line.encode("utf-8")) > self._config.max_bytes:
            self._rotate()
        self._file.write(line)

    def _rotate(self) -> None:
        self._file.flush()
        self._file.close()
        self._file_index += 1
        self._file = self._open_file()

    def _open_file(self) -> TextIO:
        date = datetime.now(UTC).strftime("%Y%m%d")
        suffix = "" if self._file_index == 0 else f".{self._file_index}"
        return (self._config.log_dir / f"roamerd-{date}.jsonl{suffix}").open(
            "a",
            encoding="utf-8",
            buffering=8192,
        )

    def _cleanup_retention(self) -> None:
        if self._config.retention_days <= 0:
            return
        cutoff = time.time() - (self._config.retention_days * 24 * 60 * 60)
        for path in self._config.log_dir.glob("roamerd-*.jsonl*"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()

    def _remember_event_id(self, event_id: str) -> None:
        if self._config.seen_event_id_limit <= 0:
            self._seen_event_ids.clear()
            self._seen_event_ids_order.clear()
            return
        self._seen_event_ids.add(event_id)
        self._seen_event_ids_order.append(event_id)
        while len(self._seen_event_ids_order) > self._config.seen_event_id_limit:
            expired = self._seen_event_ids_order.popleft()
            self._seen_event_ids.discard(expired)

    def _cleanup_stale_action_starts(self) -> None:
        if self._config.stale_action_after_sec < 0:
            return
        now = datetime.now(UTC)
        stale_action_ids = [
            action_id
            for action_id, started_at in self._action_started_at.items()
            if (now - started_at).total_seconds() > self._config.stale_action_after_sec
        ]
        for action_id in stale_action_ids:
            self._action_started_at.pop(action_id, None)

    def _redact(self, payload: JSONDict) -> tuple[JSONDict, bool]:
        redacted = False
        clean: JSONDict = {}
        for key, value in payload.items():
            lowered = key.lower()
            if lowered in {"token", "password", "secret", "api_key"}:
                clean[key] = "[REDACTED]"
                redacted = True
            elif lowered in {"text", "transcript"} and not self._config.log_transcripts:
                clean[key] = f"[REDACTED len={len(str(value))}]"
                redacted = True
            elif lowered.endswith("audio_path") and not self._config.log_audio_paths:
                clean[key] = "[REDACTED]"
                redacted = True
            else:
                clean[key] = _json_value(value)
        return clean, redacted


def _json_value(value: JSONValue) -> JSONValue:
    return value
