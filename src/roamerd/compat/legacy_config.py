"""Legacy config.yaml to RoamerdConfig migration."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from roamerd.config.schema import (
    RoamerdConfig,
)


def migrate_legacy_config(legacy: dict[str, Any]) -> RoamerdConfig:
    drivers = _dict(legacy.get("drivers"))
    init = _dict(legacy.get("init"))
    alsa = _dict(legacy.get("alsa"))
    converse = _dict(legacy.get("converse"))
    wakeword = _dict(converse.get("wakeword"))
    endpoint = _dict(converse.get("endpoint"))
    stt = _dict(converse.get("stt"))
    discord = _dict(converse.get("discord"))
    motion = _dict(legacy.get("motion"))
    logging = _dict(legacy.get("logging"))
    serve = _dict(legacy.get("serve"))
    bluetooth = _dict(legacy.get("bluetooth"))
    fswebcam = _dict(legacy.get("fswebcam"))
    piper = _dict(legacy.get("piper"))
    edge = _dict(legacy.get("edge"))
    silero = _dict(legacy.get("silero"))
    funasr = _dict(legacy.get("funasr"))
    valetudo = _dict(legacy.get("valetudo"))

    named_points = _dict(motion.get("named_points"))
    places: dict[str, dict[str, Any]] = {}
    for name, point in named_points.items():
        point_dict = _dict(point)
        places[str(name)] = {
            "pose": {
                "x": point_dict.get("x", 0),
                "y": point_dict.get("y", 0),
                "angle": point_dict.get("angle"),
                "frame": "valetudo_pixel",
            },
            "radius": motion.get("arrival_tolerance", 150),
        }

    data: dict[str, Any] = {
        "runtime": {
            "state_dir": _get(_dict(legacy.get("runtime")), "state_dir", "/run/roamer"),
            "supervisor": {
                "startup": {
                    "connect_speaker_on_startup": init.get("connect_speaker_on_startup", False),
                    "configure_proxy_on_startup": init.get("configure_proxy_on_startup", False),
                    "ensure_control_bridge_on_startup": init.get("ensure_serve_on_startup", False),
                    "control_bridge_start_timeout_sec": init.get("serve_start_timeout_sec", 10.0),
                    "proxy_init_script": init.get("proxy_init_script", ""),
                    "proxy_init_timeout_sec": init.get("proxy_init_timeout_sec", 20.0),
                    "bluetooth_controller_ready_timeout_sec": init.get(
                        "bluetooth_controller_ready_timeout_sec", 20.0
                    ),
                    "bluetooth_connect_retry_timeout_sec": init.get(
                        "bluetooth_connect_retry_timeout_sec", 20.0
                    ),
                    "bluetooth_retry_interval_sec": init.get("bluetooth_retry_interval_sec", 1.0),
                }
            },
            "logging": {
                "enabled": logging.get("enabled", True),
                "level": logging.get("level", "INFO"),
                "dir": logging.get("dir", "logs"),
                "rotation": {
                    "max_bytes": logging.get("max_bytes", 10 * 1024 * 1024),
                    "backup_count": logging.get("backup_count", 10),
                },
                "retention_days": logging.get("retention_days", 3),
            },
        },
        "kernel": {
            "state": {
                "playback_stale_after_sec": _get(
                    _dict(legacy.get("runtime")), "playback_stale_after_sec", 120.0
                )
            },
            "observability": {
                "privacy": {
                    "log_transcripts": logging.get("log_transcripts", True),
                    "log_audio_paths": logging.get("log_audio_paths", False),
                }
            },
        },
        "capabilities": {
            "hearing": {
                "audio": {
                    "driver": drivers.get("audio", "alsa"),
                    "alsa": {
                        "capture_device": alsa.get("capture_device", "hw:2,0"),
                        "sample_rate": alsa.get("sample_rate", 16000),
                        "channels": alsa.get("channels", 2),
                    },
                },
                "wakeword": {
                    "enabled": wakeword.get("enabled", True),
                    "driver": wakeword.get("driver", "su03t_gpio"),
                    "model": wakeword.get("model", ""),
                    "threshold": wakeword.get("threshold", 0.5),
                    "min_interval_sec": wakeword.get("min_interval_sec", 1.5),
                    "prompt_sound": wakeword.get("prompt_sound", False),
                    "phrases": wakeword.get("phrases", []),
                    "su03t_gpio": {
                        "gpio_chip": wakeword.get("gpio_chip", "gpiochip0"),
                        "gpio_line": wakeword.get("gpio_line", 17),
                        "edge": wakeword.get("edge", "rising"),
                        "pull": wakeword.get("pull", "down"),
                        "debounce_ms": wakeword.get("debounce_ms", 300),
                    },
                },
                "preroll": {
                    "pre_roll_sec": wakeword.get("pre_roll_sec", 1.0),
                    "chunk_duration_sec": stt.get("chunk_duration_sec", 0.1),
                },
                "followup": {
                    "timeout_sec": wakeword.get("followup_timeout_sec", 3.0),
                    "continuous_enabled": wakeword.get("continuous_followup_enabled", True),
                    "max_turns": wakeword.get("max_followup_turns", 3),
                },
                "endpoint": {
                    "mode": endpoint.get("mode", "vad_endpoint"),
                    "silence_sec": endpoint.get("silence_sec", 1.5),
                    "min_speech_sec": endpoint.get("min_speech_sec", 0.2),
                    "max_record_sec": endpoint.get("max_record_sec", 10.0),
                    "pre_speech_padding_sec": endpoint.get("pre_speech_padding_sec", 0.3),
                },
                "stt": {
                    "mode": stt.get("mode", "realtime_with_batch_fallback"),
                    "provider": stt.get("provider", "vllm_realtime"),
                    "batch_driver": drivers.get("asr", "funasr"),
                    "fallback": stt.get("fallback", "batch"),
                    "network_asr": {
                        "url": stt.get("url", ""),
                        "model": stt.get("model", "qwen3-asr-0.6b"),
                        "chunk_duration_sec": stt.get("chunk_duration_sec", 0.1),
                        "response_timeout_sec": stt.get("response_timeout_sec", 20.0),
                    },
                    "funasr": {
                        "model": funasr.get("model", "paraformer-zh-streaming"),
                        "disable_update": funasr.get("disable_update", True),
                    },
                },
                "vad": {
                    "driver": drivers.get("vad", "silero"),
                    "silero": {
                        "model": silero.get("model", "~/models/silero-vad/silero_vad.onnx"),
                        "threshold": silero.get("threshold", 0.5),
                    },
                },
                "session": {
                    "enabled": converse.get("enabled", True),
                    "silence_timeout_sec": converse.get("silence_timeout", 2.5),
                    "max_turns": converse.get("max_turns", 1),
                },
            },
            "speech": {
                "playback": {
                    "driver": drivers.get("audio", "alsa"),
                    "alsa": {
                        "playback_device": alsa.get("playback_device", "default"),
                        "sample_rate": alsa.get("sample_rate", 16000),
                        "channels": alsa.get("channels", 2),
                    },
                },
                "tts": {
                    "primary": drivers.get("tts", "edge"),
                    "piper": piper,
                    "edge": edge,
                },
                "bluetooth": {
                    "driver": drivers.get("bluetooth", "bluez"),
                    "speaker_mac": bluetooth.get("speaker_mac"),
                },
                "no_sound_default": converse.get("no_sound_default", False),
            },
            "vision": {
                "camera": {
                    "driver": drivers.get("camera", "fswebcam"),
                    "fswebcam": fswebcam,
                }
            },
            "motion": {
                "driver": "ros2_nav",
                "wait_timeout_sec": motion.get("wait_timeout_sec", 300),
                "poll_interval_sec": motion.get("poll_interval_sec", 2),
                "arrival_tolerance": motion.get("arrival_tolerance", 150),
            },
        },
        "bridges": {
            "control": {
                "enabled": serve.get("enabled", True),
                "socket": serve.get("socket", "/run/roamer/roamer.sock"),
                "request_timeout_sec": serve.get("request_timeout_sec", 60.0),
                "compat": {"fallback_to_cli": serve.get("fallback_to_cli", True)},
            },
            "discord": discord,
        },
        "policy": {
            "local_intents": converse.get("intents", []),
            "local_voice": {
                "ignore_wake_while_speaking": wakeword.get("ignore_while_speaking", True),
                "stop_phrases": wakeword.get("stop_phrases", []),
                "wake_phrases": wakeword.get("phrases", []),
                "pre_roll_sec": wakeword.get("pre_roll_sec", 1.0),
                "followup_timeout_sec": wakeword.get("followup_timeout_sec", 3.0),
                "continuous_followup_enabled": wakeword.get("continuous_followup_enabled", True),
                "max_followup_turns": wakeword.get("max_followup_turns", 3),
            },
        },
        "world_model": {"places": places},
        "ros2": {
            "valetudo_bridge": {
                "host": valetudo.get("host", "10.0.0.226"),
                "port": valetudo.get("port", 80),
                "timeout_sec": valetudo.get("timeout_sec", 8.0),
            }
        },
    }
    return RoamerdConfig.model_validate(data)


def load_config(path: Path | None = None) -> RoamerdConfig:
    legacy_config = importlib.import_module("roamer.platform.config")
    loaded = legacy_config.load_config(path)
    return migrate_legacy_config(_dict(loaded))


def migrated_leaf_paths(config: RoamerdConfig) -> set[str]:
    dumped = config.model_dump()
    return _leaf_paths(dumped)


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _get(mapping: dict[str, Any], key: str, default: Any) -> Any:
    return mapping.get(key, default)


def _leaf_paths(value: object, prefix: str = "") -> set[str]:
    if isinstance(value, dict):
        paths: set[str] = set()
        for key, child in value.items():
            paths.update(_leaf_paths(child, f"{prefix}.{key}" if prefix else str(key)))
        return paths
    return {prefix}
