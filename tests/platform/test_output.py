"""Tests for output utilities."""

import json

from roamer.platform.contract import SCHEMA_VERSION
from roamer.platform.output import attach_contract_fields, error, success


def test_success_basic():
    """Test basic success response."""
    result = success(path="/tmp/test.jpg", width=1280)
    assert result["ok"] is True
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["path"] == "/tmp/test.jpg"
    assert result["width"] == 1280


def test_success_empty():
    """Test success with no extra fields."""
    result = success()
    assert result == {"ok": True, "schema_version": SCHEMA_VERSION}


def test_error_basic():
    """Test basic error response."""
    result = error("camera_not_found", "No camera at /dev/video0")
    assert result["ok"] is False
    assert result["error"] == "camera_not_found"
    assert result["error_code"] == "camera.not_found"
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["message"] == "No camera at /dev/video0"


def test_error_with_extra_fields():
    """Test error with additional fields."""
    result = error("timeout", "Operation timed out", duration=5.0)
    assert result["ok"] is False
    assert result["error"] == "timeout"
    assert result["error_code"] == "timeout"
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["duration"] == 5.0


def test_output_is_valid_json():
    """Test that output can be serialized to JSON."""
    result = success(data={"nested": True, "list": [1, 2, 3]})
    serialized = json.dumps(result)
    assert isinstance(serialized, str)
    parsed = json.loads(serialized)
    assert parsed["ok"] is True
    assert parsed["data"]["nested"] is True


def test_attach_contract_fields_for_failure_backfills_required_keys():
    """Failed payloads should gain deterministic contract fields."""
    payload = attach_contract_fields({"ok": False}, "watch")
    assert payload["ok"] is False
    assert payload["command"] == "watch"
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["error"] == "runtime_error"
    assert payload["message"] == "Unknown runtime error"


def test_attach_contract_fields_preserves_existing_fields():
    """Existing payload keys should not be overwritten."""
    payload = attach_contract_fields(
        {
            "ok": False,
            "schema_version": "9.9",
            "error": "audio_play_failed",
            "message": "boom",
            "extra": 1,
        },
        "audio.play",
    )
    assert payload["schema_version"] == "9.9"
    assert payload["command"] == "audio.play"
    assert payload["error"] == "audio_play_failed"
    assert payload["message"] == "boom"
    assert payload["extra"] == 1
