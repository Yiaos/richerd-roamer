"""Tests for camera driver and capability."""

from unittest.mock import MagicMock, patch

import pytest

from roamer.drivers.camera.fswebcam import FswebcamDriver


class TestFswebcamDriver:
    """Tests for FswebcamDriver."""

    def test_snap_success(self):
        """Test successful image capture."""
        driver = FswebcamDriver({"device": "/dev/video0"})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.stat") as mock_stat:
                    mock_stat.return_value = MagicMock(st_size=102400)
                    result = driver.snap("/tmp/test.jpg", 1280, 720)

        assert result["ok"] is True
        assert result["path"] == "/tmp/test.jpg"
        assert result["width"] == 1280
        assert result["height"] == 720
        assert result["size_bytes"] == 102400

    def test_snap_failure_nonzero_return(self):
        """Test capture failure with non-zero return code."""
        driver = FswebcamDriver({"device": "/dev/video0"})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stderr=b"No device found"
            )
            result = driver.snap("/tmp/test.jpg", 1280, 720)

        assert result["ok"] is False
        assert result["error"] == "camera_capture_failed"
        assert "No device found" in result["details"]

    def test_snap_timeout(self):
        """Test capture timeout."""
        import subprocess

        driver = FswebcamDriver({"device": "/dev/video0"})

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="fswebcam", timeout=10)
            result = driver.snap("/tmp/test.jpg", 1280, 720)

        assert result["ok"] is False
        assert result["error"] == "camera_capture_failed"
        assert "timed out" in result["message"]

    def test_snap_fswebcam_not_installed(self):
        """Test when fswebcam is not installed."""
        driver = FswebcamDriver({"device": "/dev/video0"})

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = driver.snap("/tmp/test.jpg", 1280, 720)

        assert result["ok"] is False
        assert result["error"] == "camera_capture_failed"
        assert "not installed" in result["message"]

    def test_snap_uses_config_device(self):
        """Test that driver uses device from config."""
        driver = FswebcamDriver({"device": "/dev/video1"})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.stat") as mock_stat:
                    mock_stat.return_value = MagicMock(st_size=1000)
                    driver.snap("/tmp/test.jpg", 640, 480)

        # Check that -d /dev/video1 was passed
        call_args = mock_run.call_args[0][0]
        assert "-d" in call_args
        device_idx = call_args.index("-d")
        assert call_args[device_idx + 1] == "/dev/video1"


@pytest.mark.hardware
class TestCameraHardware:
    """Hardware tests - require actual camera."""

    def test_snap_real_hardware(self):
        """Test actual image capture."""
        driver = FswebcamDriver({"device": "/dev/video0"})
        result = driver.snap("/tmp/roamer_hw_test.jpg", 1280, 720)
        assert result["ok"] is True
        assert result["size_bytes"] > 0
