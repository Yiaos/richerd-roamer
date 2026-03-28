"""Tests for ASR driver."""

from unittest.mock import MagicMock, patch

import pytest

from roamer.drivers.speech.asr.funasr import FunASRDriver


class TestFunASRDriver:
    """Tests for FunASRDriver."""

    def test_transcribe_success(self):
        """Test successful transcription."""
        driver = FunASRDriver({"model": "paraformer-zh"})

        mock_model = MagicMock()
        mock_model.generate.return_value = [{"text": "你好世界", "confidence": 0.95}]

        with patch("pathlib.Path.exists", return_value=True):
            driver._model = mock_model
            result = driver.transcribe("/tmp/test.wav")

        assert result["ok"] is True
        assert result["text"] == "你好世界"
        assert result["confidence"] == 0.95

    def test_transcribe_file_not_found(self):
        """Test when audio file not found."""
        driver = FunASRDriver({"model": "paraformer-zh"})

        with patch("pathlib.Path.exists", return_value=False):
            result = driver.transcribe("/nonexistent/audio.wav")

        assert result["ok"] is False
        assert result["error"] == "asr_failed"
        assert "not found" in result["message"]

    def test_transcribe_empty_result(self):
        """Test when transcription returns empty."""
        driver = FunASRDriver({"model": "paraformer-zh"})

        mock_model = MagicMock()
        mock_model.generate.return_value = [{"text": ""}]

        with patch("pathlib.Path.exists", return_value=True):
            driver._model = mock_model
            result = driver.transcribe("/tmp/test.wav")

        assert result["ok"] is True
        assert result["text"] == ""

    def test_transcribe_model_error(self):
        """Test when model raises error."""
        driver = FunASRDriver({"model": "paraformer-zh"})

        mock_model = MagicMock()
        mock_model.generate.side_effect = Exception("Model error")

        with patch("pathlib.Path.exists", return_value=True):
            driver._model = mock_model
            result = driver.transcribe("/tmp/test.wav")

        assert result["ok"] is False
        assert result["error"] == "asr_failed"

    def test_load_model_import_error(self):
        """Test when funasr not installed."""
        driver = FunASRDriver({"model": "paraformer-zh"})

        with patch.dict("sys.modules", {"funasr": None}):
            with patch("builtins.__import__", side_effect=ImportError):
                loaded = driver._load_model()

        assert loaded is False


@pytest.mark.hardware
class TestASRHardware:
    """Hardware tests - require actual FunASR model."""

    def test_transcribe_real_model(self):
        """Test with actual FunASR model."""
        # This test requires a pre-recorded WAV file with speech
        pass
