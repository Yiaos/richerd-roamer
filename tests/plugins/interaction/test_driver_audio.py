"""Tests for audio driver and capability."""

import io
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from roamer.plugins.interaction.drivers.audio.alsa import AlsaDriver


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

    def test_stream_chunks_uses_arecord_stdout_and_stops_process(self):
        """Chunk capture should stream raw PCM from arecord stdout."""
        driver = AlsaDriver({
            "capture_device": "hw:1,0",
            "sample_rate": 1000,
            "channels": 2,
        })
        process = MagicMock()
        process.stdout = io.BytesIO(b"a" * 40 + b"b" * 40)
        process.poll.return_value = None

        with patch("subprocess.Popen", return_value=process) as mock_popen:
            chunks = list(driver.stream_chunks(chunk_duration_sec=0.01, max_duration_sec=0.02))

        assert chunks == [b"a" * 40, b"b" * 40]
        cmd = mock_popen.call_args[0][0]
        assert cmd == [
            "arecord",
            "-D",
            "hw:1,0",
            "-f",
            "S16_LE",
            "-r",
            "1000",
            "-c",
            "2",
            "-t",
            "raw",
        ]
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=1)

    def test_stream_chunks_accepts_unbounded_duration(self):
        """Long-running wake service can stream until arecord closes stdout."""
        driver = AlsaDriver({
            "capture_device": "hw:1,0",
            "sample_rate": 1000,
            "channels": 2,
        })
        process = MagicMock()
        process.stdout = io.BytesIO(b"a" * 40 + b"b" * 40)
        process.poll.return_value = None

        with patch("subprocess.Popen", return_value=process):
            chunks = list(driver.stream_chunks(chunk_duration_sec=0.01, max_duration_sec=None))

        assert chunks == [b"a" * 40, b"b" * 40]
        process.terminate.assert_called_once()

    def test_stream_chunks_close_stops_process_before_exhaustion(self):
        """Pre-roll stop can terminate the active arecord stream from another owner."""
        driver = AlsaDriver({
            "capture_device": "hw:1,0",
            "sample_rate": 1000,
            "channels": 2,
        })
        process = MagicMock()
        process.stdout = io.BytesIO(b"a" * 40 + b"b" * 40)
        process.poll.return_value = None

        with patch("subprocess.Popen", return_value=process):
            chunks = driver.stream_chunks(chunk_duration_sec=0.01, max_duration_sec=None)
            assert next(chunks) == b"a" * 40
            chunks.close()

        process.terminate.assert_called_once()

    def test_stream_chunks_missing_arecord_raises_dependency_error(self):
        driver = AlsaDriver({"capture_device": "hw:1,0"})

        with patch("subprocess.Popen", side_effect=FileNotFoundError):
            try:
                list(driver.stream_chunks())
            except FileNotFoundError:
                pass
            else:  # pragma: no cover
                raise AssertionError("expected FileNotFoundError")

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
