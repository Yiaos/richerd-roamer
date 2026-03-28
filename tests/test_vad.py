"""Tests for VAD driver."""

import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


class TestSileroDriver:
    """Tests for SileroDriver."""

    def test_detect_with_speech(self):
        """Test detection with speech present."""
        # Mock onnxruntime before importing driver
        mock_ort = MagicMock()
        mock_session = MagicMock()
        mock_session.run.return_value = [
            np.array([[0.9]]),
            np.zeros((2, 1, 128), dtype=np.float32),
        ]
        mock_ort.InferenceSession.return_value = mock_session

        with patch.dict(sys.modules, {"onnxruntime": mock_ort}):
            from roamer.drivers.speech.vad.silero import SileroDriver

            driver = SileroDriver({"model": "/models/silero_vad.onnx", "threshold": 0.5})

            with patch("pathlib.Path.exists", return_value=True):
                audio = np.random.randn(16000).astype(np.float32) * 0.1
                result = driver.detect(audio, 16000)

        assert result["ok"] is True
        assert result["speech_detected"] is True
        assert len(result["segments"]) > 0

    def test_detect_no_speech(self):
        """Test detection with no speech."""
        mock_ort = MagicMock()
        mock_session = MagicMock()
        mock_session.run.return_value = [
            np.array([[0.1]]),
            np.zeros((2, 1, 128), dtype=np.float32),
        ]
        mock_ort.InferenceSession.return_value = mock_session

        with patch.dict(sys.modules, {"onnxruntime": mock_ort}):
            from roamer.drivers.speech.vad.silero import SileroDriver

            driver = SileroDriver({"model": "/models/silero_vad.onnx", "threshold": 0.5})

            with patch("pathlib.Path.exists", return_value=True):
                audio = np.zeros(16000, dtype=np.float32)
                result = driver.detect(audio, 16000)

        assert result["ok"] is True
        assert result["speech_detected"] is False
        assert len(result["segments"]) == 0

    def test_detect_model_not_found(self):
        """Test when model file not found."""
        from roamer.drivers.speech.vad.silero import SileroDriver

        driver = SileroDriver({"model": "/nonexistent/model.onnx"})

        with patch("pathlib.Path.exists", return_value=False):
            audio = np.zeros(16000, dtype=np.float32)
            result = driver.detect(audio, 16000)

        assert result["ok"] is False
        assert result["error"] == "vad_failed"

    def test_detect_stereo_audio(self):
        """Test with stereo audio input."""
        mock_ort = MagicMock()
        mock_session = MagicMock()
        mock_session.run.return_value = [
            np.array([[0.9]]),
            np.zeros((2, 1, 128), dtype=np.float32),
        ]
        mock_ort.InferenceSession.return_value = mock_session

        with patch.dict(sys.modules, {"onnxruntime": mock_ort}):
            from roamer.drivers.speech.vad.silero import SileroDriver

            driver = SileroDriver({"model": "/models/silero_vad.onnx", "threshold": 0.5})

            with patch("pathlib.Path.exists", return_value=True):
                # Stereo audio
                audio = np.random.randn(16000, 2).astype(np.float32) * 0.1
                result = driver.detect(audio, 16000)

        assert result["ok"] is True

    def test_detect_resampling(self):
        """Test with different sample rate."""
        mock_ort = MagicMock()
        mock_session = MagicMock()
        mock_session.run.return_value = [
            np.array([[0.9]]),
            np.zeros((2, 1, 128), dtype=np.float32),
        ]
        mock_ort.InferenceSession.return_value = mock_session

        with patch.dict(sys.modules, {"onnxruntime": mock_ort}):
            from roamer.drivers.speech.vad.silero import SileroDriver

            driver = SileroDriver({"model": "/models/silero_vad.onnx", "threshold": 0.5})

            with patch("pathlib.Path.exists", return_value=True):
                # 44.1kHz audio
                audio = np.random.randn(44100).astype(np.float32) * 0.1
                result = driver.detect(audio, 44100)

        assert result["ok"] is True


@pytest.mark.hardware
class TestVADHardware:
    """Hardware tests - require actual silero model."""

    def test_detect_real_model(self):
        """Test with actual silero model."""
        from roamer.drivers.speech.vad.silero import SileroDriver

        driver = SileroDriver({
            "model": "~/models/silero-vad/silero_vad.onnx",
            "threshold": 0.5,
        })
        # Test with silence
        audio = np.zeros(16000, dtype=np.float32)
        result = driver.detect(audio, 16000)
        assert result["ok"] is True
