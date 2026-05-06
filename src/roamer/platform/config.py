"""Configuration loading and management."""

import os
from pathlib import Path
from typing import Any

import yaml


def default_repo_config_path() -> Path:
    """Return default repo-local config path (project root/config.yaml)."""
    return Path(__file__).resolve().parents[3] / "config.yaml"


def default_proxy_init_script_path() -> Path:
    """Return the repo-local proxy init script path."""
    return default_repo_config_path().parent / "scripts" / "init-roamer-proxy.sh"


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
    "init": {
        "connect_speaker_on_startup": False,
        "configure_proxy_on_startup": False,
        "ensure_serve_on_startup": False,
        "serve_start_timeout_sec": 10.0,
        "proxy_init_script": "",
        "proxy_init_timeout_sec": 20.0,
        "bluetooth_controller_ready_timeout_sec": 20.0,
        "bluetooth_connect_retry_timeout_sec": 20.0,
        "bluetooth_retry_interval_sec": 1.0,
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
        "disable_update": True,
    },
    "valetudo": {
        "timeout_sec": 8.0,
    },
    "motion": {
        "wait_timeout_sec": 300,
        "poll_interval_sec": 2,
        "arrival_tolerance": 150,
    },
    "bluetooth": {
        "speaker_mac": None,
    },
    "serve": {
        "enabled": True,
        "socket": "/run/roamer/roamer.sock",
        "request_timeout_sec": 60.0,
        "fallback_to_cli": True,
    },
    "logging": {
        "enabled": True,
        "level": "INFO",
        "dir": "/var/log/roamer",
        "max_bytes": 10 * 1024 * 1024,
        "backup_count": 10,
        "retention_days": 3,
        "log_transcripts": True,
        "log_audio_paths": False,
    },
    "converse": {
        "enabled": True,
        "silence_timeout": 2.5,
        "max_turns": 10,
        "no_sound_default": False,
        "wakeword": {
            "enabled": True,
            "driver": "su03t_gpio",
            "model": "",
            "threshold": 0.5,
            "gpio_chip": "gpiochip0",
            "gpio_line": 17,
            "edge": "rising",
            "pull": "down",
            "debounce_ms": 300,
            "min_interval_sec": 1.5,
            "pre_roll_sec": 0.8,
            "ignore_while_speaking": True,
            "prompt_sound": False,
            "phrases": ["richard", "rich erd", "瑞彻德"],
            "followup_timeout_sec": 10.0,
        },
        "intents": [
            {"name": "time_now", "action": "time.now", "patterns": ["现在几点", "几点了"]},
            {"name": "status", "action": "sense", "patterns": ["你在哪", "状态"]},
            {"name": "watch", "action": "watch", "patterns": ["看一下", "拍张照"]},
            {"name": "go_home", "action": "motion.home", "patterns": ["回家", "回充电"]},
            {
                "name": "position",
                "action": "motion.position",
                "patterns": ["你在哪个位置", "当前位置"],
            },
        ],
        "endpoint": {
            "mode": "vad_endpoint",
            "silence_sec": 2.0,
            "min_speech_sec": 0.2,
            "max_record_sec": 10.0,
            "pre_speech_padding_sec": 0.3,
        },
        "discord": {
            "enabled": False,
            "channel_id": "",
            "token_env": "DISCORD_BOT_TOKEN",
            "source": "roamer",
            "mention_user_id": "",
            "mention_role_id": "",
            "mention": "",
            "reply_instruction": "通过 Roamer 语音回复",
        },
    },
}


def resolve_config_path(path: Path | None = None) -> Path | None:
    """Resolve the effective config path for runtime and CLI callers."""
    if path is not None:
        return path

    env_path = os.environ.get("ROAMER_CONFIG")
    if env_path:
        return Path(env_path).expanduser()

    repo_config = default_repo_config_path()
    if repo_config.exists():
        return repo_config

    return None


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load configuration from file, merging with defaults."""
    config = _deep_copy(DEFAULT_CONFIG)
    resolved_path = resolve_config_path(path)

    if resolved_path is not None and resolved_path.exists():
        with open(resolved_path) as f:
            user_config = yaml.safe_load(f) or {}
        _deep_merge(config, user_config)

    _apply_dynamic_defaults(config)
    return config


def _apply_dynamic_defaults(config: dict[str, Any]) -> None:
    """Fill defaults that depend on the installed repository location."""
    init_config = config.setdefault("init", {})
    if not init_config.get("proxy_init_script"):
        init_config["proxy_init_script"] = str(default_proxy_init_script_path())


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
