"""Pytest configuration and fixtures."""

import pytest


def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers", "hardware: mark test as requiring physical hardware"
    )


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        "drivers": {
            "camera": "fswebcam",
            "audio": "alsa",
            "tts": "piper",
            "asr": "funasr",
            "vad": "silero",
            "bluetooth": "bluez",
        },
        "fswebcam": {
            "device": "/dev/video0",
            "width": 1280,
            "height": 720,
        },
        "alsa": {
            "capture_device": "hw:2,0",
            "playback_device": "default",
            "sample_rate": 16000,
            "channels": 2,
        },
    }
