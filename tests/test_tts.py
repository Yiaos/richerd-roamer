"""Tests for TTS driver."""

from unittest.mock import MagicMock, patch

import pytest

from roamer.drivers.speech.tts.piper import PiperDriver


class TestPiperDriver:
    """Tests for PiperDriver."""

    def test_synthesize_success(self):
        """Test successful synthesis."""
        driver = PiperDriver({
            "binary": "/usr/bin/piper",
            "model": "/models/zh.onnx",
        })

        with patch("pathlib.Path.exists", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                with patch.object(driver, "_get_wav_duration", return_value=1.5):
                    result = driver.synthesize("测试", "/tmp/test.wav")

        assert result["ok"] is True
        assert result["text"] == "测试"
        assert result["duration_sec"] == 1.5

    def test_synthesize_binary_not_found(self):
        """Test when piper binary not found."""
        driver = PiperDriver({
            "binary": "/nonexistent/piper",
            "model": "/models/zh.onnx",
        })

        with patch("pathlib.Path.exists") as mock_exists:
            mock_exists.side_effect = lambda: False
            result = driver.synthesize("测试", "/tmp/test.wav")

        assert result["ok"] is False
        assert result["error"] == "tts_failed"

    def test_synthesize_failure(self):
        """Test synthesis failure."""
        driver = PiperDriver({
            "binary": "/usr/bin/piper",
            "model": "/models/zh.onnx",
        })

        with patch("pathlib.Path.exists", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1,
                    stderr=b"Model error",
                )
                result = driver.synthesize("测试", "/tmp/test.wav")

        assert result["ok"] is False
        assert result["error"] == "tts_failed"


@pytest.mark.hardware
class TestTTSHardware:
    """Hardware tests - require actual Piper installation."""

    def test_synthesize_real(self):
        """Test actual synthesis."""
        driver = PiperDriver({
            "binary": "~/bin/piper/piper",
            "model": "~/models/piper/zh_CN-huayan-medium.onnx",
        })
        result = driver.synthesize("你好世界", "/tmp/roamer_tts_test.wav")
        assert result["ok"] is True
