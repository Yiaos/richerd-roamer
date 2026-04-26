"""Tests for configuration loading."""

import tempfile
from pathlib import Path

from roamer.platform.config import get_driver_config, get_driver_name, load_config


def test_load_default_config(tmp_path, monkeypatch):
    """Test loading built-in defaults when no default config exists."""
    monkeypatch.delenv("ROAMER_CONFIG", raising=False)
    monkeypatch.setattr(
        "roamer.platform.config.default_repo_config_path",
        lambda: tmp_path / "missing-repo.yaml",
    )

    config = load_config(None)

    assert "drivers" in config
    assert config["drivers"]["camera"] == "fswebcam"
    assert config["drivers"]["audio"] == "alsa"
    assert config["drivers"]["tts"] == "piper"


def test_load_custom_config():
    """Test loading custom configuration file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("drivers:\n  camera: libcamera\n")
        f.flush()
        config = load_config(Path(f.name))
        assert config["drivers"]["camera"] == "libcamera"
        # Other defaults should still be present
        assert config["drivers"]["audio"] == "alsa"


def test_load_nonexistent_config():
    """Test loading from non-existent path returns defaults."""
    config = load_config(Path("/nonexistent/config.yaml"))
    assert config["drivers"]["camera"] == "fswebcam"


def test_get_driver_name():
    """Test getting driver name for capability."""
    config = {"drivers": {"camera": "fswebcam", "audio": "pulseaudio"}}
    assert get_driver_name(config, "camera") == "fswebcam"
    assert get_driver_name(config, "audio") == "pulseaudio"


def test_get_driver_name_default():
    """Test getting default driver name when not specified."""
    config = {"drivers": {}}
    assert get_driver_name(config, "camera") == "fswebcam"
    assert get_driver_name(config, "motion") == "valetudo"


def test_get_driver_config():
    """Test getting driver-specific configuration."""
    config = {
        "fswebcam": {"device": "/dev/video1", "width": 640},
    }
    driver_config = get_driver_config(config, "fswebcam")
    assert driver_config["device"] == "/dev/video1"
    assert driver_config["width"] == 640


def test_get_driver_config_default():
    """Test getting default driver configuration."""
    config = {}
    driver_config = get_driver_config(config, "fswebcam")
    assert driver_config["device"] == "/dev/video0"
    assert driver_config["width"] == 1280


def test_deep_merge():
    """Test that nested configs are properly merged."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("fswebcam:\n  device: /dev/video1\n")
        f.flush()
        config = load_config(Path(f.name))
        # Overridden value
        assert config["fswebcam"]["device"] == "/dev/video1"
        # Default value preserved
        assert config["fswebcam"]["width"] == 1280


def test_default_config_includes_serve_and_endpoint_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("ROAMER_CONFIG", raising=False)
    monkeypatch.setattr(
        "roamer.platform.config.default_repo_config_path",
        lambda: tmp_path / "missing-repo.yaml",
    )

    config = load_config(None)

    assert config["serve"]["enabled"] is True
    assert config["serve"]["fallback_to_cli"] is True
    assert config["serve"]["prewarm"]["asr"] is True
    assert config["converse"]["endpoint"]["mode"] == "fixed_recording"
    assert config["converse"]["endpoint"]["silence_sec"] == 2.0
