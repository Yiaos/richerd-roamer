"""JSONL observability trace logger."""

from __future__ import annotations

import contextlib
import contextvars
import json
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TextIO

from pydantic import BaseModel, Field

from roamerd.config.schema import ObservabilityPrivacyConfig, RuntimeLoggingConfig
from roamerd.contracts.action import Action
from roamerd.contracts.privacy import redact_payload
from roamerd.events.base import Event, JSONDict
from roamerd.kernel.event_bus import EventBus

_turn_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("turn_id", default=None)
_action_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("action_id", default=None)
_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)


class TraceEntry(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    level: str = "info"
    event_type: str
    session_id: str
    turn_id: str | None = None
    action_id: str | None = None
    correlation_id: str | None = None
    request_id: str | None = None
    source: str = ""
    payload: JSONDict = Field(default_factory=dict)
    redacted: bool = False


class TraceLogger:
    def __init__(
        self,
        config: RuntimeLoggingConfig,
        privacy: ObservabilityPrivacyConfig,
        *,
        session_id: str,
    ) -> None:
        self._config = config
        self._privacy = privacy
        self._session_id = session_id
        self._path: Path | None = None
        self._handle: TextIO | None = None
        if config.enabled:
            log_dir = Path(config.dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            self._prune_old_logs(log_dir)
            self._path = log_dir / f"roamerd-{datetime.now(timezone.utc).date().isoformat()}.jsonl"
            self._handle = self._open_handle()

    async def start(self, bus: EventBus) -> None:
        bus.subscribe_pattern("*", self._on_event)

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

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
        clean, redacted = redact_payload(
            payload,
            log_transcripts=self._privacy.log_transcripts,
            log_audio_paths=self._privacy.log_audio_paths,
        )
        entry = TraceEntry(
            level=level,
            event_type=event_type,
            session_id=self._session_id,
            turn_id=turn_id or _turn_id.get(),
            action_id=action_id or _action_id.get(),
            correlation_id=correlation_id or _correlation_id.get(),
            request_id=request_id,
            source=source,
            payload=clean,
            redacted=redacted,
        )
        self._write(entry)

    def log_action_start(self, action: Action) -> None:
        self.log(
            "action.started",
            {"action_type": action.action_type, "resource": action.resource},
            action_id=action.action_id,
        )

    def log_action_end(self, action: Action, result: JSONDict) -> None:
        self.log(f"action.{action.status.value}", result, action_id=action.action_id)

    async def _on_event(self, event: Event) -> None:
        self.log(
            event.event_type,
            event.payload,
            source=event.source,
            turn_id=event.turn_id,
            action_id=event.action_id,
            correlation_id=event.correlation_id,
            request_id=_request_id_from_payload(event.payload),
        )

    def _write(self, entry: TraceEntry) -> None:
        if self._handle is None:
            return
        line = json.dumps(entry.model_dump(mode="json"), ensure_ascii=False) + "\n"
        self._rotate_if_needed(len(line.encode("utf-8")))
        if self._handle is None:
            return
        self._handle.write(line)
        if entry.level == "error" or entry.event_type.startswith("safety."):
            self._handle.flush()

    def _open_handle(self) -> TextIO:
        if self._path is None:
            raise RuntimeError("log path not configured")
        return open(self._path, "a", buffering=8192)

    def _rotate_if_needed(self, incoming_bytes: int) -> None:
        if self._path is None or self._handle is None:
            return
        max_bytes = self._config.rotation.max_bytes
        if max_bytes <= 0:
            return
        self._handle.flush()
        current_size = self._path.stat().st_size if self._path.exists() else 0
        if current_size + incoming_bytes <= max_bytes:
            return
        self._handle.close()
        self._handle = None
        self._rotate_backups()
        self._handle = self._open_handle()

    def _rotate_backups(self) -> None:
        if self._path is None:
            return
        backup_count = max(self._config.rotation.backup_count, 0)
        if backup_count == 0:
            self._path.unlink(missing_ok=True)
            return
        oldest = Path(f"{self._path}.{backup_count}")
        oldest.unlink(missing_ok=True)
        for index in range(backup_count - 1, 0, -1):
            source = Path(f"{self._path}.{index}")
            if source.exists():
                source.rename(Path(f"{self._path}.{index + 1}"))
        if self._path.exists():
            self._path.rename(Path(f"{self._path}.1"))

    def _prune_old_logs(self, log_dir: Path) -> None:
        if self._config.retention_days < 0:
            return
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=self._config.retention_days)
        for path in log_dir.glob("roamerd-*.jsonl*"):
            date = _date_from_log_path(path)
            if date is not None and date < cutoff:
                path.unlink(missing_ok=True)


def _request_id_from_payload(payload: JSONDict) -> str | None:
    value = payload.get("request_id")
    return str(value) if isinstance(value, str) and value else None


def _date_from_log_path(path: Path) -> date | None:
    stem = path.name.removeprefix("roamerd-").split(".jsonl", 1)[0]
    try:
        return datetime.fromisoformat(stem).date()
    except ValueError:
        return None
