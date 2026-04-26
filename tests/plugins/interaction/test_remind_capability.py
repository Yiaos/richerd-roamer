"""Tests for reminder scheduling capability."""

from unittest.mock import patch

from roamer.plugins.interaction.capabilities.remind import RemindCapability, parse_delay


def test_parse_delay_supports_minutes_and_seconds() -> None:
    assert parse_delay("60s") == 60
    assert parse_delay("5m") == 300
    assert parse_delay("10分钟") == 600


def test_remind_schedule_spawns_detached_process() -> None:
    capability = RemindCapability({})

    with patch("roamer.plugins.interaction.capabilities.remind.subprocess.Popen") as mock_popen:
        mock_popen.return_value.pid = 1234
        result = capability.schedule(delay_sec=60, text="喝水")

    assert result["ok"] is True
    assert result["scheduled"] is True
    assert result["delay_sec"] == 60.0
    assert result["text"] == "喝水"
    assert result["pid"] == 1234
    args = mock_popen.call_args.args[0]
    assert args[0]
    assert "提醒：喝水" in args[2]
