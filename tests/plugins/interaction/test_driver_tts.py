"""Tests for TTS drivers."""

from unittest.mock import MagicMock, patch

import pytest

from roamer.platform.contract import ErrorCode
from roamer.plugins.interaction.drivers.speech.tts.edge import EdgeDriver
from roamer.plugins.interaction.drivers.speech.tts.piper import PiperDriver


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

        with patch("pathlib.Path.exists", return_value=False):
            result = driver.synthesize("测试", "/tmp/test.wav")

        assert result["ok"] is False
        assert result["error"] == "tts_failed"
        assert result["error_code"] == ErrorCode.DEPENDENCY_TTS_PIPER_BINARY_MISSING

    def test_synthesize_timeout(self):
        """Test piper synthesis timeout."""
        import subprocess as sp

        driver = PiperDriver({
            "binary": "/usr/bin/piper",
            "model": "/models/zh.onnx",
        })

        with patch("pathlib.Path.exists", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = sp.TimeoutExpired("piper", 30)
                result = driver.synthesize("测试", "/tmp/test.wav")

        assert result["ok"] is False
        assert result["error"] == "tts_failed"
        assert result["error_code"] == ErrorCode.SPEECH_TTS_TIMEOUT

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

    def test_synthesize_ignores_style(self):
        """Test style parameter is accepted and ignored for Piper."""
        driver = PiperDriver({
            "binary": "/usr/bin/piper",
            "model": "/models/zh.onnx",
        })

        with patch("pathlib.Path.exists", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                with patch.object(driver, "_get_wav_duration", return_value=1.5):
                    result = driver.synthesize("测试", "/tmp/test.wav", style="cheerful")

        assert result["ok"] is True
        assert result["text"] == "测试"


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


class TestEdgeDriver:
    """Tests for EdgeDriver."""

    def test_synthesize_success_mp3(self):
        """Test successful synthesis to MP3."""
        driver = EdgeDriver({"voice": "zh-CN-YunxiNeural"})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("pathlib.Path.exists", return_value=True):
                with patch.object(driver, "_get_audio_duration", return_value=2.5):
                    result = driver.synthesize("测试", "/tmp/test.mp3")

        assert result["ok"] is True
        assert result["text"] == "测试"
        assert result["duration_sec"] == 2.5
        assert result["voice"] == "zh-CN-YunxiNeural"

    def test_synthesize_success_wav_conversion(self):
        """Test successful synthesis with WAV conversion."""
        driver = EdgeDriver({"voice": "zh-CN-YunxiNeural"})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.unlink"):
                    with patch.object(driver, "_get_audio_duration", return_value=2.0):
                        result = driver.synthesize("测试", "/tmp/test.wav")

        assert result["ok"] is True
        assert result["text"] == "测试"
        # Two calls: edge-tts and ffmpeg
        assert mock_run.call_count == 2

    def test_synthesize_edge_tts_not_found(self):
        """Test when edge-tts not installed."""
        driver = EdgeDriver({})

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = driver.synthesize("测试", "/tmp/test.mp3")

        assert result["ok"] is False
        assert result["error"] == "tts_failed"
        assert result["error_code"] == ErrorCode.DEPENDENCY_TTS_EDGE_TTS_MISSING
        assert "edge-tts not found" in result["message"]

    def test_synthesize_timeout(self):
        """Test synthesis timeout."""
        import subprocess as sp

        driver = EdgeDriver({})

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = sp.TimeoutExpired("edge-tts", 60)
            result = driver.synthesize("测试", "/tmp/test.mp3")

        assert result["ok"] is False
        assert result["error"] == "tts_failed"
        assert result["error_code"] == ErrorCode.SPEECH_TTS_TIMEOUT
        assert "timed out" in result["message"]

    def test_synthesize_wav_conversion_failed(self):
        """Test ffmpeg conversion failure returns canonical convert error code."""
        driver = EdgeDriver({})

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # edge-tts synthesis
                MagicMock(returncode=1),  # ffmpeg conversion
            ]
            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.unlink"):
                    result = driver.synthesize("测试", "/tmp/test.wav")

        assert result["ok"] is False
        assert result["error"] == "tts_failed"
        assert result["error_code"] == ErrorCode.AUDIO_CONVERT_FAILED

    def test_synthesize_failure(self):
        """Test edge-tts command failure."""
        driver = EdgeDriver({})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr=b"Connection error",
            )
            result = driver.synthesize("测试", "/tmp/test.mp3")

        assert result["ok"] is False
        assert result["error"] == "tts_failed"

    def test_custom_voice_config(self):
        """Test custom voice configuration."""
        driver = EdgeDriver({
            "voice": "en-US-AriaNeural",
            "rate": "+20%",
            "volume": "-10%",
        })

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("pathlib.Path.exists", return_value=True):
                with patch.object(driver, "_get_audio_duration", return_value=1.0):
                    driver.synthesize("Hello", "/tmp/test.mp3")

        # Check the command arguments include custom config
        call_args = mock_run.call_args[0][0]
        assert "--voice" in call_args
        assert "en-US-AriaNeural" in call_args
        assert "--rate" in call_args
        assert "+20%" in call_args

    def test_synthesize_with_valid_style_uses_ssml(self):
        """Test valid style switches Edge TTS to SSML mode."""
        driver = EdgeDriver({"voice": "zh-CN-YunxiNeural"})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("pathlib.Path.exists", return_value=True):
                with patch.object(driver, "_get_audio_duration", return_value=2.5):
                    result = driver.synthesize("测试", "/tmp/test.mp3", style="cheerful")

        call_args = mock_run.call_args[0][0]
        assert "--ssml" in call_args
        assert "--text" not in call_args
        assert "mstts:express-as style='cheerful'" in call_args[call_args.index("--ssml") + 1]
        assert result["style"] == "cheerful"

    def test_synthesize_with_invalid_style_falls_back_to_text(self):
        """Test invalid style falls back to plain text synthesis."""
        driver = EdgeDriver({"voice": "zh-CN-YunxiNeural"})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("pathlib.Path.exists", return_value=True):
                with patch.object(driver, "_get_audio_duration", return_value=2.5):
                    result = driver.synthesize("测试", "/tmp/test.mp3", style="invalid")

        call_args = mock_run.call_args[0][0]
        assert "--text" in call_args
        assert "--ssml" not in call_args
        assert result["style"] == "invalid"


@pytest.mark.hardware
class TestEdgeDriverHardware:
    """Hardware tests - require network and edge-tts."""

    def test_synthesize_real_mp3(self):
        """Test actual Edge TTS synthesis to MP3."""
        driver = EdgeDriver({"voice": "zh-CN-YunxiNeural"})
        result = driver.synthesize("你好，我是Roamer", "/tmp/roamer_edge_test.mp3")
        assert result["ok"] is True
        assert result["duration_sec"] is not None

    def test_synthesize_real_wav(self):
        """Test actual Edge TTS synthesis to WAV (with conversion)."""
        driver = EdgeDriver({"voice": "zh-CN-YunxiNeural"})
        result = driver.synthesize("你好，我是Roamer", "/tmp/roamer_edge_test.wav")
        assert result["ok"] is True
