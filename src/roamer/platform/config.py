"""Configuration loading and management."""

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG: dict[str, Any] = {
    "drivers": {
        "camera": "fswebcam",
        "audio": "alsa",
        "tts": "piper",
        "asr": "funasr",
        "vad": "silero",
        "motion": "valetudo",
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
    "piper": {
        "binary": "~/bin/piper/piper",
        "model": "~/models/piper/zh_CN-huayan-medium.onnx",
    },
    "silero": {
        "model": "~/models/silero-vad/silero_vad.onnx",
        "threshold": 0.5,
    },
    "funasr": {
        "model": "paraformer-zh-streaming",
    },
    "valetudo": {
        "host": "10.0.0.100",
        "port": 80,
    },
}


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load configuration from file, merging with defaults."""
    config = _deep_copy(DEFAULT_CONFIG)

    if path is not None and path.exists():
        with open(path) as f:
            user_config = yaml.safe_load(f) or {}
        _deep_merge(config, user_config)

    return config


def get_driver_name(config: dict[str, Any], capability: str) -> str:
    """Get the driver name for a capability."""
    return config.get("drivers", {}).get(capability, DEFAULT_CONFIG["drivers"].get(capability, ""))


def get_driver_config(config: dict[str, Any], driver_name: str) -> dict[str, Any]:
    """Get configuration for a specific driver."""
    return config.get(driver_name, DEFAULT_CONFIG.get(driver_name, {}))


def _deep_copy(d: dict) -> dict:
    """Create a deep copy of a dictionary."""
    result = {}
    for k, v in d.items():
        if isinstance(v, dict):
            result[k] = _deep_copy(v)
        elif isinstance(v, list):
            result[k] = v.copy()
        else:
            result[k] = v
    return result


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge override into base, modifying base in-place."""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
