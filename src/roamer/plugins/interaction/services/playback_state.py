"""Cross-process playback state for wake/speak coordination."""

from __future__ import annotations

import fcntl
import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any


class PlaybackState:
    """File-backed playback markers under a shared runtime state directory."""

    def __init__(self, state_dir: str | Path, *, stale_after_sec: float = 120.0):
        self.state_dir = Path(state_dir).expanduser()
        self.marker_dir = self.state_dir / "playback.d"
        self.json_path = self.state_dir / "playback.json"
        self.state_lock_path = self.state_dir / "playback.state.lock"
        self.stale_after_sec = float(stale_after_sec)

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "PlaybackState":
        runtime_cfg = config.get("runtime", {})
        return cls(
            runtime_cfg.get("state_dir", "/run/roamer"),
            stale_after_sec=float(runtime_cfg.get("playback_stale_after_sec", 120.0)),
        )

    def is_active(self) -> bool:
        try:
            return bool(self.snapshot().get("active", False))
        except OSError:
            return False

    def generation(self) -> int:
        try:
            return int(self.snapshot().get("generation") or 0)
        except OSError:
            return 0

    def snapshot(self) -> dict[str, Any]:
        try:
            with self._locked():
                return self._sync_snapshot_unlocked()
        except OSError:
            return {"active": False, "active_count": 0, "generation": 0, "unavailable": True}

    def mark_started(
        self,
        *,
        request_id: str | None = None,
        source: str = "speak",
        text_hash: str | None = None,
    ) -> dict[str, Any]:
        playback_id = uuid.uuid4().hex
        with self._locked():
            current = self._sync_snapshot_unlocked()
            generation = int(current.get("generation") or 0)
            marker = {
                "active": True,
                "playback_id": playback_id,
                "request_id": request_id,
                "source": source,
                "text_hash": text_hash,
                "pid": os.getpid(),
                "started_at": _now_iso(),
                "started_at_epoch": time.time(),
                "expires_at_epoch": time.time() + self.stale_after_sec,
                "generation": generation,
            }
            self._write_marker_unlocked(marker)
            markers = self._active_markers_unlocked()
            self._write_snapshot_unlocked(markers=markers, generation=generation)
            return marker

    def mark_finished(
        self,
        *,
        playback_id: str | None = None,
        request_id: str | None = None,
        source: str = "speak",
    ) -> dict[str, Any]:
        with self._locked():
            current = self._sync_snapshot_unlocked()
            before = self._active_markers_unlocked()
            removed = self._remove_matching_markers_unlocked(
                playback_id=playback_id,
                request_id=request_id,
                source=source,
            )
            after = self._active_markers_unlocked()
            generation = int(current.get("generation") or 0)
            if removed and before and not after:
                generation += 1
            return self._write_snapshot_unlocked(
                markers=after,
                generation=generation,
                finished_at=_now_iso(),
                last_marker=removed[-1] if removed else None,
            )

    @contextmanager
    def _locked(self):
        self.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.marker_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        with open(self.state_lock_path, "a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _sync_snapshot_unlocked(self) -> dict[str, Any]:
        current = self._read_snapshot_unlocked()
        previous_active_count = int(
            current.get("active_count") or (1 if current.get("active") else 0)
        )
        markers = self._active_markers_unlocked(prune_stale=True)
        generation = int(current.get("generation") or 0)
        if previous_active_count > 0 and not markers:
            generation += 1
        return self._write_snapshot_unlocked(
            markers=markers,
            generation=generation,
            last_marker=None if markers else current,
        )

    def _read_snapshot_unlocked(self) -> dict[str, Any]:
        try:
            with open(self.json_path, encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {"active": False, "active_count": 0, "generation": 0}
        if not isinstance(data, dict):
            return {"active": False, "active_count": 0, "generation": 0}
        data.setdefault("active", False)
        data.setdefault("active_count", 1 if data.get("active") else 0)
        data.setdefault("generation", 0)
        return data

    def _active_markers_unlocked(self, *, prune_stale: bool = False) -> list[dict[str, Any]]:
        markers: list[dict[str, Any]] = []
        for path in sorted(self.marker_dir.glob("*.json")):
            marker = self._read_marker(path)
            if marker is None:
                if prune_stale:
                    path.unlink(missing_ok=True)
                continue
            if prune_stale and self._is_marker_stale(marker):
                path.unlink(missing_ok=True)
                continue
            markers.append(marker)
        return markers

    def _remove_matching_markers_unlocked(
        self,
        *,
        playback_id: str | None,
        request_id: str | None,
        source: str,
    ) -> list[dict[str, Any]]:
        removed: list[dict[str, Any]] = []
        for path in sorted(self.marker_dir.glob("*.json")):
            marker = self._read_marker(path)
            if marker is None:
                path.unlink(missing_ok=True)
                continue
            if playback_id is not None:
                matches = marker.get("playback_id") == playback_id
            elif request_id is not None:
                matches = marker.get("request_id") == request_id
            else:
                matches = False
            if matches and marker.get("source") == source:
                path.unlink(missing_ok=True)
                removed.append(marker)
        return removed

    def _write_snapshot_unlocked(
        self,
        *,
        markers: list[dict[str, Any]],
        generation: int,
        finished_at: str | None = None,
        last_marker: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        latest = markers[-1] if markers else (last_marker or {})
        state = {
            "active": bool(markers),
            "active_count": len(markers),
            "generation": generation,
            "request_id": latest.get("request_id"),
            "source": latest.get("source"),
            "text_hash": latest.get("text_hash"),
            "started_at": latest.get("started_at"),
            "finished_at": None if markers else finished_at or latest.get("finished_at"),
            "markers": [
                {
                    "playback_id": marker.get("playback_id"),
                    "request_id": marker.get("request_id"),
                    "source": marker.get("source"),
                    "pid": marker.get("pid"),
                    "started_at": marker.get("started_at"),
                    "text_hash": marker.get("text_hash"),
                }
                for marker in markers
            ],
        }
        self._write_json(self.json_path, state)
        return state

    def _write_marker_unlocked(self, marker: dict[str, Any]) -> None:
        self._write_json(self.marker_dir / f"{marker['playback_id']}.json", marker)

    def _write_json(self, path: Path, state: dict[str, Any]) -> None:
        tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, separators=(",", ":"))
        tmp_path.replace(path)

    def _read_marker(self, path: Path) -> dict[str, Any] | None:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        return data if isinstance(data, dict) else None

    def _is_marker_stale(self, marker: dict[str, Any]) -> bool:
        expires_at = marker.get("expires_at_epoch")
        if isinstance(expires_at, (int, float)) and time.time() > float(expires_at):
            return True

        pid = marker.get("pid")
        if isinstance(pid, int) and pid > 0:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            except PermissionError:
                return False

        started_at = marker.get("started_at_epoch")
        if isinstance(started_at, (int, float)) and self.stale_after_sec > 0:
            return time.time() - float(started_at) > self.stale_after_sec
        return False


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")
