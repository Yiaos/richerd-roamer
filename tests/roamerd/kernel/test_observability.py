import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from roamerd.config.schema import (
    ObservabilityPrivacyConfig,
    RuntimeLoggingConfig,
    RuntimeLoggingRotationConfig,
)
from roamerd.events import make_event
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.observability import TraceLogger


def test_trace_logger_promotes_request_id_from_event_payload(tmp_path: Path) -> None:
    async def scenario() -> dict[str, object]:
        bus = EventBus(session_id="s")
        logger = TraceLogger(
            RuntimeLoggingConfig(dir=str(tmp_path)),
            ObservabilityPrivacyConfig(),
            session_id="s",
        )
        await logger.start(bus)
        await bus.publish(
            make_event(
                "control.command_received",
                source="control",
                session_id="s",
                payload={"request_id": "req-1", "command": "status"},
                correlation_id="corr-1",
            )
        )
        await bus.drain_once()
        logger.close()
        log_file = next(tmp_path.glob("roamerd-*.jsonl"))
        return json.loads(log_file.read_text().splitlines()[0])

    entry = asyncio.run(scenario())
    assert entry["request_id"] == "req-1"
    assert entry["correlation_id"] == "corr-1"
    assert entry["payload"]["request_id"] == "req-1"


def test_trace_logger_redacts_transcripts_when_configured(tmp_path: Path) -> None:
    logger = TraceLogger(
        RuntimeLoggingConfig(dir=str(tmp_path)),
        ObservabilityPrivacyConfig(log_transcripts=False),
        session_id="s",
    )

    logger.log("hearing.transcript_ready", {"text": "秘密内容"}, source="test")
    logger.close()

    log_file = next(tmp_path.glob("roamerd-*.jsonl"))
    entry = json.loads(log_file.read_text().splitlines()[0])
    assert entry["payload"]["text"] == "[REDACTED len=4]"
    assert entry["redacted"] is True


def test_trace_logger_rotates_when_current_log_exceeds_max_bytes(tmp_path: Path) -> None:
    logger = TraceLogger(
        RuntimeLoggingConfig(
            dir=str(tmp_path),
            rotation=RuntimeLoggingRotationConfig(max_bytes=500, backup_count=2),
        ),
        ObservabilityPrivacyConfig(),
        session_id="s",
    )

    for index in range(3):
        logger.log("test.large", {"index": index, "text": "x" * 80}, source="test")
    logger.close()

    active = next(tmp_path.glob("roamerd-*.jsonl"))
    rotated = Path(f"{active}.1")
    assert active.exists()
    assert rotated.exists()
    assert active.stat().st_size <= 500
    assert rotated.stat().st_size > 0


def test_trace_logger_deletes_files_older_than_retention_days(tmp_path: Path) -> None:
    old_date = (datetime.now(timezone.utc) - timedelta(days=10)).date().isoformat()
    old_file = tmp_path / f"roamerd-{old_date}.jsonl"
    old_file.write_text("{}\n")

    logger = TraceLogger(
        RuntimeLoggingConfig(dir=str(tmp_path), retention_days=3),
        ObservabilityPrivacyConfig(),
        session_id="s",
    )
    logger.close()

    assert not old_file.exists()
