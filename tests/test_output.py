"""Tests for output utilities."""

import json

from roamer.output import error, success


def test_success_basic():
    """Test basic success response."""
    result = success(path="/tmp/test.jpg", width=1280)
    assert result["ok"] is True
    assert result["path"] == "/tmp/test.jpg"
    assert result["width"] == 1280


def test_success_empty():
    """Test success with no extra fields."""
    result = success()
    assert result == {"ok": True}


def test_error_basic():
    """Test basic error response."""
    result = error("camera_not_found", "No camera at /dev/video0")
    assert result["ok"] is False
    assert result["error"] == "camera_not_found"
    assert result["message"] == "No camera at /dev/video0"


def test_error_with_extra_fields():
    """Test error with additional fields."""
    result = error("timeout", "Operation timed out", duration=5.0)
    assert result["ok"] is False
    assert result["error"] == "timeout"
    assert result["duration"] == 5.0


def test_output_is_valid_json():
    """Test that output can be serialized to JSON."""
    result = success(data={"nested": True, "list": [1, 2, 3]})
    serialized = json.dumps(result)
    assert isinstance(serialized, str)
    parsed = json.loads(serialized)
    assert parsed["ok"] is True
    assert parsed["data"]["nested"] is True
