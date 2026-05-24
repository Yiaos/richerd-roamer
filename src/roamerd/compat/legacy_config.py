from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field

from roamerd.config.schema import PlaceConfig, RoamerdConfig


class MigrationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mapped_keys: list[str] = Field(default_factory=list)
    ignored_keys: dict[str, str] = Field(default_factory=dict)
    unmapped_leaf_keys: list[str] = Field(default_factory=list)


def migrate_legacy_config(path: Path) -> tuple[RoamerdConfig, MigrationReport]:
    legacy = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(legacy, dict):
        legacy = {}
    legacy_config = {str(key): item for key, item in legacy.items()}
    leaves = _leaf_keys(legacy)
    mapped_keys = sorted(key for key in leaves if _is_mapped_leaf(key))
    unmapped_keys = sorted(key for key in leaves if not _is_mapped_leaf(key))
    report = MigrationReport(
        mapped_keys=mapped_keys,
        ignored_keys={
            "converse.discord": "Discord bridge settings moved to telegram bridge compatibility.",
            "converse.endpoint": "Endpoint tuning is folded into hearing session/VAD config.",
            "converse.intents": "Legacy intent seeds are replaced by policy.local_intents.",
            "funasr.disable_update": "Model package update behavior is outside roamerd runtime.",
            "logging": "Logging policy is handled by the roamerd observability layer.",
            "valetudo.http_moved_to_ros2": (
                "Valetudo HTTP config is consumed by the ROS 2 bridge, not roamerd motion."
            ),
        },
        unmapped_leaf_keys=unmapped_keys,
    )

    config = RoamerdConfig()
    _map_drivers(config, legacy_config)
    _map_init(config, legacy_config)
    _map_audio(config, legacy_config)
    _map_speech(config, legacy_config)
    _map_hearing(config, legacy_config)
    _map_vision(config, legacy_config)
    _map_motion(config, legacy_config)
    _map_bridges(config, legacy_config)
    _map_runtime(config, legacy_config)
    _map_ros2(config, legacy_config)
    return config, report


def _leaf_keys(value: object, prefix: str = "") -> list[str]:
    if not isinstance(value, dict):
        return [prefix]
    leaves: list[str] = []
    for key, item in value.items():
        child_prefix = f"{prefix}.{key}" if prefix else str(key)
        leaves.extend(_leaf_keys(item, child_prefix))
    return leaves


def _section(legacy: Mapping[str, object], name: str) -> dict[str, object]:
    value = legacy.get(name, {})
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _string(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _float(value: object, default: float) -> float:
    if isinstance(value, str | int | float):
        return float(value)
    return default


def _int(value: object, default: int) -> int:
    if isinstance(value, str | int | float):
        return int(value)
    return default


def _map_drivers(config: RoamerdConfig, legacy: Mapping[str, object]) -> None:
    drivers = _section(legacy, "drivers")
    audio_driver = _string(drivers.get("audio"), "mock")
    config.capabilities.hearing.audio.driver = audio_driver
    config.capabilities.speech.playback.driver = audio_driver
    config.capabilities.hearing.vad.driver = _string(drivers.get("vad"), "mock")
    config.capabilities.hearing.stt.batch_driver = _string(drivers.get("asr"), "mock")
    config.capabilities.speech.tts.primary = _driver_alias(
        _string(drivers.get("tts"), "mock"),
        {"edge": "edge_tts"},
    )
    config.capabilities.vision.camera.driver = _string(drivers.get("camera"), "mock")
    config.capabilities.speech.bluetooth.driver = _string(drivers.get("bluetooth"), "mock")
    if drivers.get("motion"):
        config.capabilities.motion.driver = "ros2_nav"


def _map_init(config: RoamerdConfig, legacy: Mapping[str, object]) -> None:
    init = _section(legacy, "init")
    startup = config.runtime.supervisor.startup
    startup.connect_speaker_on_startup = bool(init.get("connect_speaker_on_startup", False))
    startup.configure_proxy_on_startup = bool(init.get("configure_proxy_on_startup", False))
    startup.ensure_control_bridge_on_startup = bool(init.get("ensure_serve_on_startup", False))
    startup.control_bridge_start_timeout_sec = _float(init.get("serve_start_timeout_sec"), 10.0)
    startup.proxy_init_timeout_sec = _float(init.get("proxy_init_timeout_sec"), 20.0)
    startup.bluetooth_controller_ready_timeout_sec = _float(
        init.get("bluetooth_controller_ready_timeout_sec"), 20.0
    )
    startup.bluetooth_connect_retry_timeout_sec = _float(
        init.get("bluetooth_connect_retry_timeout_sec"), 20.0
    )
    startup.bluetooth_retry_interval_sec = _float(init.get("bluetooth_retry_interval_sec"), 1.0)
    startup.proxy_init_script = str(
        Path(__file__).resolve().parents[3] / "scripts" / "init-roamer-proxy.sh"
    )


def _map_audio(config: RoamerdConfig, legacy: Mapping[str, object]) -> None:
    alsa = _section(legacy, "alsa")
    hearing_alsa = config.capabilities.hearing.alsa
    speech_alsa = config.capabilities.speech.alsa
    hearing_alsa.capture_device = _string(alsa.get("capture_device"), hearing_alsa.capture_device)
    speech_alsa.capture_device = hearing_alsa.capture_device
    speech_alsa.playback_device = _string(
        alsa.get("playback_device"), speech_alsa.playback_device
    )
    hearing_alsa.playback_device = speech_alsa.playback_device
    hearing_alsa.sample_rate = _int(alsa.get("sample_rate"), hearing_alsa.sample_rate)
    speech_alsa.sample_rate = hearing_alsa.sample_rate
    hearing_alsa.channels = _int(alsa.get("channels"), hearing_alsa.channels)
    speech_alsa.channels = hearing_alsa.channels


def _map_speech(config: RoamerdConfig, legacy: Mapping[str, object]) -> None:
    piper = _section(legacy, "piper")
    edge = _section(legacy, "edge")
    bluetooth = _section(legacy, "bluetooth")
    config.capabilities.speech.tts.piper_binary = _string(piper.get("binary"))
    config.capabilities.speech.tts.piper_model = _string(piper.get("model"))
    config.capabilities.speech.tts.edge_voice = _string(
        edge.get("voice"), "zh-CN-YunxiNeural"
    )
    speaker_mac = bluetooth.get("speaker_mac")
    config.capabilities.speech.bluetooth.speaker_mac = (
        str(speaker_mac) if speaker_mac is not None else None
    )


def _map_hearing(config: RoamerdConfig, legacy: Mapping[str, object]) -> None:
    silero = _section(legacy, "silero")
    converse = _section(legacy, "converse")
    wakeword = _section(converse, "wakeword")
    stt = _section(converse, "stt")
    session = config.capabilities.hearing.session
    session.enabled = bool(converse.get("enabled", True))
    session.silence_timeout = _float(converse.get("silence_timeout"), 2.5)
    session.max_turns = _int(converse.get("max_turns"), 1)
    session.no_sound_default = bool(converse.get("no_sound_default", False))
    config.capabilities.hearing.vad.silero.model = _string(silero.get("model"))
    config.capabilities.hearing.vad.silero.threshold = _float(silero.get("threshold"), 0.1)
    config.capabilities.hearing.wakeword = config.capabilities.hearing.wakeword.model_copy(
        update=cast(Mapping[str, Any], wakeword)
    )
    config.capabilities.hearing.stt = config.capabilities.hearing.stt.model_copy(
        update=cast(Mapping[str, Any], stt)
    )
    config.capabilities.hearing.stt.provider = _driver_alias(
        config.capabilities.hearing.stt.provider,
        {"vllm_realtime": "network_asr"},
    )


def _map_vision(config: RoamerdConfig, legacy: Mapping[str, object]) -> None:
    camera = _section(legacy, "fswebcam")
    config.capabilities.vision.camera.device = _string(camera.get("device"), "/dev/video0")
    config.capabilities.vision.camera.width = _int(camera.get("width"), 1280)
    config.capabilities.vision.camera.height = _int(camera.get("height"), 720)


def _map_motion(config: RoamerdConfig, legacy: Mapping[str, object]) -> None:
    motion = _section(legacy, "motion")
    config.capabilities.motion.wait_timeout_sec = _float(motion.get("wait_timeout_sec"), 300.0)
    config.capabilities.motion.poll_interval_sec = _float(motion.get("poll_interval_sec"), 2.0)
    config.capabilities.motion.arrival_tolerance = _float(motion.get("arrival_tolerance"), 150.0)
    named_points = _section(motion, "named_points")
    config.world_model.places = {
        str(name): PlaceConfig(
            x=_float(point.get("x"), 0.0),
            y=_float(point.get("y"), 0.0),
            angle=_float(point.get("angle"), 0.0) if point.get("angle") is not None else None,
        )
        for name, point in named_points.items()
        if isinstance(point, dict) and "x" in point and "y" in point
    }


def _map_bridges(config: RoamerdConfig, legacy: Mapping[str, object]) -> None:
    serve = _section(legacy, "serve")
    discord = _section(_section(legacy, "converse"), "discord")
    config.bridges.control.enabled = bool(serve.get("enabled", True))
    config.bridges.control.socket = _string(serve.get("socket"), "/run/roamer/roamer.sock")
    config.bridges.control.request_timeout_sec = _float(serve.get("request_timeout_sec"), 60.0)
    config.bridges.control.fallback_to_cli = bool(serve.get("fallback_to_cli", True))
    config.bridges.telegram.enabled = bool(discord.get("enabled", False))
    config.bridges.telegram.channel_id = _string(discord.get("channel_id"))
    config.bridges.telegram.token_env = "ROAMERD_TELEGRAM_BOT_TOKEN"


def _map_runtime(config: RoamerdConfig, legacy: Mapping[str, object]) -> None:
    runtime = _section(legacy, "runtime")
    config.runtime.state_dir = _string(runtime.get("state_dir"), "/run/roamer")
    config.runtime.playback_stale_after_sec = _float(
        runtime.get("playback_stale_after_sec"), 120.0
    )


def _map_ros2(config: RoamerdConfig, legacy: Mapping[str, object]) -> None:
    valetudo = _section(legacy, "valetudo")
    config.ros2.valetudo_bridge.host = _string(valetudo.get("host"))
    config.ros2.valetudo_bridge.port = _int(valetudo.get("port"), 80)
    config.ros2.valetudo_bridge.timeout_sec = _float(valetudo.get("timeout_sec"), 8.0)


def _driver_alias(value: str, aliases: Mapping[str, str]) -> str:
    return aliases.get(value, value)


def _is_mapped_leaf(key: str) -> bool:
    exact = {
        "alsa.capture_device",
        "alsa.playback_device",
        "alsa.sample_rate",
        "alsa.channels",
        "bluetooth.speaker_mac",
        "converse.enabled",
        "converse.max_turns",
        "converse.no_sound_default",
        "converse.silence_timeout",
        "converse.intents",
        "drivers.asr",
        "drivers.audio",
        "drivers.bluetooth",
        "drivers.camera",
        "drivers.motion",
        "drivers.tts",
        "drivers.vad",
        "edge.rate",
        "edge.voice",
        "edge.volume",
        "fswebcam.device",
        "fswebcam.height",
        "fswebcam.width",
        "funasr.disable_update",
        "funasr.model",
        "init.bluetooth_connect_retry_timeout_sec",
        "init.bluetooth_controller_ready_timeout_sec",
        "init.configure_proxy_on_startup",
        "init.connect_speaker_on_startup",
        "init.ensure_serve_on_startup",
        "init.proxy_init_timeout_sec",
        "init.serve_start_timeout_sec",
        "init.bluetooth_retry_interval_sec",
        "motion.arrival_tolerance",
        "motion.poll_interval_sec",
        "motion.wait_timeout_sec",
        "piper.binary",
        "piper.model",
        "runtime.playback_stale_after_sec",
        "runtime.state_dir",
        "serve.enabled",
        "serve.fallback_to_cli",
        "serve.request_timeout_sec",
        "serve.socket",
        "silero.model",
        "silero.threshold",
        "valetudo.host",
        "valetudo.port",
        "valetudo.timeout_sec",
    }
    prefixes = (
        "converse.discord.",
        "converse.endpoint.",
        "converse.stt.",
        "converse.wakeword.",
        "logging.",
        "motion.named_points.",
    )
    return key in exact or key.startswith(prefixes)
