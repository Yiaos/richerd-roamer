import json
import os
import time
from pathlib import Path

import pytest

from roamerd.events import Event
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.observability import TraceLogger, TraceLoggerConfig


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for file_path in sorted(path.glob("roamerd-*.jsonl*"))
        for line in file_path.read_text(encoding="utf-8").splitlines()
    ]


def test_log_writes_jsonl_with_context_and_request_id(tmp_path: Path) -> None:
    logger = TraceLogger(TraceLoggerConfig(log_dir=tmp_path), session_id="session-1")

    with (
        logger.bind_turn("turn-1"),
        logger.bind_action("action-1"),
        logger.bind_correlation("corr-1"),
    ):
        logger.log(
            "action.started",
            {"action_type": "speech.speak"},
            source="action_manager",
            request_id="req-1",
        )
    logger.close()

    [entry] = read_jsonl(tmp_path)
    assert entry["event_type"] == "action.started"
    assert entry["session_id"] == "session-1"
    assert entry["turn_id"] == "turn-1"
    assert entry["action_id"] == "action-1"
    assert entry["correlation_id"] == "corr-1"
    assert entry["request_id"] == "req-1"
    assert entry["payload"] == {"action_type": "speech.speak"}


def test_redacts_transcripts_and_audio_paths_when_disabled(tmp_path: Path) -> None:
    logger = TraceLogger(
        TraceLoggerConfig(log_dir=tmp_path, log_transcripts=False, log_audio_paths=False),
        session_id="session-1",
    )

    logger.log(
        "hearing.transcript_ready",
        {"text": "hello world", "audio_path": "/tmp/in.wav", "token": "secret"},
    )
    logger.close()

    [entry] = read_jsonl(tmp_path)
    assert entry["redacted"] is True
    assert entry["payload"] == {
        "text": "[REDACTED len=11]",
        "audio_path": "[REDACTED]",
        "token": "[REDACTED]",
    }


@pytest.mark.asyncio
async def test_subscribe_records_bus_events(tmp_path: Path) -> None:
    bus = EventBus()
    logger = TraceLogger(TraceLoggerConfig(log_dir=tmp_path), session_id="session-1")
    await logger.start(bus)

    await bus.publish(
        Event(
            event_type="system.handler_timeout",
            source="event_bus",
            session_id="session-1",
            payload={"event_type": "hearing.transcript_ready", "timeout_sec": 5.0},
        )
    )
    await bus.run_until_idle()
    logger.close()

    [entry] = read_jsonl(tmp_path)
    assert entry["event_type"] == "system.handler_timeout"
    assert entry["source"] == "event_bus"
    assert entry["payload"] == {"event_type": "hearing.transcript_ready", "timeout_sec": 5.0}


@pytest.mark.asyncio
async def test_bus_subscription_does_not_duplicate_same_event_id(tmp_path: Path) -> None:
    bus = EventBus()
    logger = TraceLogger(TraceLoggerConfig(log_dir=tmp_path), session_id="session-1")
    await logger.start(bus)
    event = Event(
        event_type="system.handler_timeout",
        source="event_bus",
        session_id="session-1",
        event_id="event-1",
        payload={"event_type": "hearing.transcript_ready"},
    )

    await bus.publish(event)
    await bus.publish(event)
    await bus.run_until_idle()
    logger.close()

    entries = read_jsonl(tmp_path)
    assert len(entries) == 1
    assert entries[0]["event_type"] == "system.handler_timeout"


def test_safety_event_flushes_immediately(tmp_path: Path) -> None:
    logger = TraceLogger(TraceLoggerConfig(log_dir=tmp_path), session_id="session-1")

    logger.log("safety.triggered", {"reason": "bumper"})

    assert read_jsonl(tmp_path)[0]["event_type"] == "safety.triggered"
    logger.close()


def test_rotation_creates_additional_jsonl_file(tmp_path: Path) -> None:
    logger = TraceLogger(
        TraceLoggerConfig(log_dir=tmp_path, max_bytes=220),
        session_id="session-1",
    )

    for index in range(6):
        logger.log("system.health_changed", {"index": index, "padding": "x" * 40})
    logger.close()

    files = sorted(tmp_path.glob("roamerd-*.jsonl*"))
    assert len(files) >= 2


def test_retention_cleanup_removes_expired_jsonl_files(tmp_path: Path) -> None:
    old_file = tmp_path / "roamerd-20200101.jsonl"
    old_file.write_text("{}\n", encoding="utf-8")
    old_timestamp = time.time() - (3 * 24 * 60 * 60)
    os.utime(old_file, (old_timestamp, old_timestamp))

    logger = TraceLogger(
        TraceLoggerConfig(log_dir=tmp_path, retention_days=1),
        session_id="session-1",
    )
    logger.close()

    assert not old_file.exists()


def test_action_helpers_record_duration(tmp_path: Path) -> None:
    logger = TraceLogger(TraceLoggerConfig(log_dir=tmp_path), session_id="session-1")

    logger.log_action_start("action-1", action_type="speech.speak", resource="speaker")
    logger.log_action_end("action-1", {"ok": True})
    logger.close()

    entries = read_jsonl(tmp_path)
    assert [entry["event_type"] for entry in entries] == ["action.started", "action.completed"]
    assert "duration_ms" in entries[1]["payload"]
