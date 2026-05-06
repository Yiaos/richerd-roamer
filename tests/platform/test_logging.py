"""Tests for Roamer structured runtime logging."""

from __future__ import annotations

import json
import time
from pathlib import Path

import roamer.platform.logging as logging_module
from roamer.platform.logging import log_event, mask_sensitive_value, request_context, setup_logging


def test_mask_sensitive_value_keeps_first_and_last_characters() -> None:
    assert mask_sensitive_value("abc123SECRETxyz789") == "abc1***z789"
    assert mask_sensitive_value("short") == "s***t"


def test_log_event_writes_jsonl_and_redacts_sensitive_fields(tmp_path: Path) -> None:
    setup_logging(
        {
            "logging": {
                "enabled": True,
                "dir": str(tmp_path),
                "max_bytes": 100_000,
                "backup_count": 2,
                "retention_days": 3,
            }
        }
    )

    log_event(
        "wake",
        "asr_transcript",
        text="瑞彻德现在几点了",
        token="abc123SECRETxyz789",
        proxy="http://user:password@example.test:8080",
    )

    line = (tmp_path / "roamer.log").read_text(encoding="utf-8").strip()
    payload = json.loads(line)

    assert payload["component"] == "wake"
    assert payload["event"] == "asr_transcript"
    assert payload["text"] == "瑞彻德现在几点了"
    assert payload["token"] == "abc1***z789"
    assert payload["proxy"] == "http://u***r:p***d@example.test:8080"


def test_log_event_adds_request_id_from_context(tmp_path: Path) -> None:
    setup_logging(
        {
            "logging": {
                "enabled": True,
                "dir": str(tmp_path),
                "max_bytes": 100_000,
                "backup_count": 2,
                "retention_days": 3,
            }
        }
    )

    with request_context("req-test-1"):
        log_event("listen", "asr_transcript", text="现在几点")
        log_event("converse", "route_text", route="local")

    lines = (tmp_path / "roamer.log").read_text(encoding="utf-8").strip().splitlines()
    payloads = [json.loads(line) for line in lines]

    assert [payload["request_id"] for payload in payloads] == ["req-test-1", "req-test-1"]


def test_setup_logging_removes_logs_older_than_retention(tmp_path: Path) -> None:
    old_log = tmp_path / "roamer.log.9"
    old_log.write_text("old", encoding="utf-8")
    old_time = time.time() - (4 * 24 * 60 * 60)
    old_log.touch()
    Path(old_log).touch()
    import os

    os.utime(old_log, (old_time, old_time))

    setup_logging(
        {
            "logging": {
                "enabled": True,
                "dir": str(tmp_path),
                "max_bytes": 100_000,
                "backup_count": 2,
                "retention_days": 3,
            }
        }
    )

    assert not old_log.exists()


def test_log_event_periodically_removes_expired_logs(tmp_path: Path) -> None:
    setup_logging(
        {
            "logging": {
                "enabled": True,
                "dir": str(tmp_path),
                "max_bytes": 100_000,
                "backup_count": 2,
                "retention_days": 3,
            }
        }
    )
    old_log = tmp_path / "roamer.log.8"
    old_log.write_text("old", encoding="utf-8")
    old_time = time.time() - (4 * 24 * 60 * 60)
    import os

    os.utime(old_log, (old_time, old_time))
    logging_module._NEXT_CLEANUP_AT = 0

    log_event("serve", "request", command="ping")

    assert not old_log.exists()
