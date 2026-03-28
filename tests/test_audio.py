"""Tests for audio driver and capability."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from roamer.drivers.audio.alsa import AlsaDriver


class TestAlsaDriver:
    """Tests for AlsaDriver."""

    def test_record_success(self):
        """Test successful recording."""
        driver = AlsaDriver({"capture_device": "hw:2,0", "sample_rate": 16000, "channels": 2})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.stat") as mock_stat:
                    mock_stat.return_value = MagicMock(st_size=320000)
                    result = driver.record("/tmp/test.wav", 5.0)

        assert result["ok"] is True
        assert result["path"] == "/tmp/test.wav"
        assert result["duration_sec"] == 5.0
        assert result["sample_rate"] == 16000
        assert result["channels"] == 2

    def test_record_failure(self):
        """Test recording failure."""
        driver = AlsaDriver({})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stderr=b"Device not found"
            )
            result = driver.record("/tmp/test.wav", 5.0)

        assert result["ok"] is False
        assert result["error"] == "audio_record_failed"

    def test_record_timeout(self):
        """Test recording timeout."""
        driver = AlsaDriver({})

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="arecord", timeout=10)
            result = driver.record("/tmp/test.wav", 5.0)

        assert result["ok"] is False
        assert result["error"] == "audio_record_failed"
        assert "timed out" in result["message"]

    def test_play_success(self):
        """Test successful playback."""
        driver = AlsaDriver({"playback_device": "default"})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch.object(driver, "_get_wav_duration", return_value=3.5):
                result = driver.play("/tmp/test.wav")

        assert result["ok"] is True
        assert result["played"] == "/tmp/test.wav"
        assert result["duration_sec"] == 3.5

    def test_play_failure(self):
        """Test playback failure."""
        driver = AlsaDriver({})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stderr=b"Cannot open device"
            )
            with patch.object(driver, "_get_wav_duration", return_value=1.0):
                result = driver.play("/tmp/test.wav")

        assert result["ok"] is False
        assert result["error"] == "audio_play_failed"

    def test_record_uses_config(self):
        """Test that driver uses config values."""
        driver = AlsaDriver({
            "capture_device": "hw:1,0",
            "sample_rate": 44100,
            "channels": 1,
        })

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.stat") as mock_stat:
                    mock_stat.return_value = MagicMock(st_size=1000)
                    driver.record("/tmp/test.wav", 2.0)

        call_args = mock_run.call_args[0][0]
        assert "-D" in call_args
        assert "hw:1,0" in call_args
        assert "-r" in call_args
        assert "44100" in call_args
        assert "-c" in call_args
        assert "1" in call_args


@pytest.mark.hardware
class TestAudioHardware:
    """Hardware tests - require actual audio devices."""

    def test_record_real_hardware(self):
        """Test actual recording."""
        driver = AlsaDriver({"capture_device": "hw:2,0", "sample_rate": 16000, "channels": 2})
        result = driver.record("/tmp/roamer_hw_audio_test.wav", 2.0)
        assert result["ok"] is True
