"""Typed roamerd configuration schema."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

from roamerd.contracts.local_intent import LocalIntentRule


class StartupConfig(BaseModel):
    connect_speaker_on_startup: bool = False
    configure_proxy_on_startup: bool = False
    ensure_control_bridge_on_startup: bool = False
    control_bridge_start_timeout_sec: float = 10.0
    proxy_init_script: str = ""
    proxy_init_timeout_sec: float = 20.0
    bluetooth_controller_ready_timeout_sec: float = 20.0
    bluetooth_connect_retry_timeout_sec: float = 20.0
    bluetooth_retry_interval_sec: float = 1.0


class SupervisorConfig(BaseModel):
    startup: StartupConfig = Field(default_factory=StartupConfig)
    health_interval_sec: float = 30.0


class RuntimeLoggingRotationConfig(BaseModel):
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 10


class RuntimeLoggingConfig(BaseModel):
    enabled: bool = True
    level: str = "INFO"
    dir: str = "logs"
    rotation: RuntimeLoggingRotationConfig = Field(default_factory=RuntimeLoggingRotationConfig)
    retention_days: int = 3


class RuntimeConfig(BaseModel):
    state_dir: str = "/run/roamer"
    supervisor: SupervisorConfig = Field(default_factory=SupervisorConfig)
    logging: RuntimeLoggingConfig = Field(default_factory=RuntimeLoggingConfig)


class ObservabilityPrivacyConfig(BaseModel):
    log_transcripts: bool = True
    log_audio_paths: bool = False


class KernelStateConfig(BaseModel):
    playback_stale_after_sec: float = 120.0


class KernelObservabilityConfig(BaseModel):
    privacy: ObservabilityPrivacyConfig = Field(default_factory=ObservabilityPrivacyConfig)


class KernelConfig(BaseModel):
    state: KernelStateConfig = Field(default_factory=KernelStateConfig)
    observability: KernelObservabilityConfig = Field(default_factory=KernelObservabilityConfig)
    handler_timeout_sec: float = 5.0
    safety_watchdog_timeout_sec: float = 1.0
    safety_watchdog_interval_sec: float = 0.1


class AlsaCaptureConfig(BaseModel):
    capture_device: str = "hw:2,0"
    sample_rate: int = 16000
    channels: int = 2


class WakewordSu03tConfig(BaseModel):
    gpio_chip: str = "gpiochip0"
    gpio_line: int = 17
    edge: str = "rising"
    pull: str = "down"
    debounce_ms: int = 300


class WakewordConfig(BaseModel):
    enabled: bool = True
    driver: str = "su03t_gpio"
    model: str = ""
    threshold: float = 0.5
    min_interval_sec: float = 1.5
    prompt_sound: bool = False
    phrases: list[str] = Field(default_factory=lambda: ["richard", "rich erd", "瑞彻德", "理查德"])
    su03t_gpio: WakewordSu03tConfig = Field(default_factory=WakewordSu03tConfig)


class PrerollConfig(BaseModel):
    pre_roll_sec: float = 1.0
    chunk_duration_sec: float = 0.1


class FollowupConfig(BaseModel):
    timeout_sec: float = 3.0
    continuous_enabled: bool = True
    max_turns: int = 3


class EndpointConfig(BaseModel):
    mode: str = "vad_endpoint"
    silence_sec: float = 1.5
    min_speech_sec: float = 0.2
    max_record_sec: float = 10.0
    pre_speech_padding_sec: float = 0.3


class NetworkAsrConfig(BaseModel):
    url: str = "ws://hurricane.tail33ee82.ts.net:8302/v1/realtime"
    model: str = "qwen3-asr-0.6b"
    chunk_duration_sec: float = 0.1
    response_timeout_sec: float = 20.0


class FunAsrConfig(BaseModel):
    model: str = "paraformer-zh-streaming"
    disable_update: bool = True


class SttConfig(BaseModel):
    mode: str = "realtime_with_batch_fallback"
    provider: str = "vllm_realtime"
    batch_driver: str = "funasr"
    fallback: str = "batch"
    network_asr: NetworkAsrConfig = Field(default_factory=NetworkAsrConfig)
    funasr: FunAsrConfig = Field(default_factory=FunAsrConfig)


class VadSileroConfig(BaseModel):
    model: str = "~/models/silero-vad/silero_vad.onnx"
    threshold: float = 0.5


class VadConfig(BaseModel):
    driver: str = "silero"
    silero: VadSileroConfig = Field(default_factory=VadSileroConfig)


class HearingSessionConfig(BaseModel):
    enabled: bool = True
    silence_timeout_sec: float = 2.5
    max_turns: int = 1


class HearingAudioConfig(BaseModel):
    driver: str = "alsa"
    alsa: AlsaCaptureConfig = Field(default_factory=AlsaCaptureConfig)


class HearingConfig(BaseModel):
    audio: HearingAudioConfig = Field(default_factory=HearingAudioConfig)
    wakeword: WakewordConfig = Field(default_factory=WakewordConfig)
    preroll: PrerollConfig = Field(default_factory=PrerollConfig)
    followup: FollowupConfig = Field(default_factory=FollowupConfig)
    endpoint: EndpointConfig = Field(default_factory=EndpointConfig)
    stt: SttConfig = Field(default_factory=SttConfig)
    vad: VadConfig = Field(default_factory=VadConfig)
    session: HearingSessionConfig = Field(default_factory=HearingSessionConfig)


class PlaybackAlsaConfig(BaseModel):
    playback_device: str = "default"
    sample_rate: int = 16000
    channels: int = 2


class PlaybackConfig(BaseModel):
    driver: str = "alsa"
    alsa: PlaybackAlsaConfig = Field(default_factory=PlaybackAlsaConfig)


class PiperConfig(BaseModel):
    binary: str = "~/bin/piper/piper"
    model: str = "~/models/piper/zh_CN-huayan-medium.onnx"


class EdgeConfig(BaseModel):
    voice: str = "zh-CN-YunxiNeural"
    rate: str = "+0%"
    volume: str = "+0%"


class TtsConfig(BaseModel):
    primary: str = "edge"
    piper: PiperConfig = Field(default_factory=PiperConfig)
    edge: EdgeConfig = Field(default_factory=EdgeConfig)


class BluetoothConfig(BaseModel):
    driver: str = "bluez"
    speaker_mac: str | None = None


class SpeechConfig(BaseModel):
    playback: PlaybackConfig = Field(default_factory=PlaybackConfig)
    tts: TtsConfig = Field(default_factory=TtsConfig)
    bluetooth: BluetoothConfig = Field(default_factory=BluetoothConfig)
    no_sound_default: bool = False


class FswebcamConfig(BaseModel):
    device: str = "/dev/video0"
    width: int = 1280
    height: int = 720


class CameraConfig(BaseModel):
    driver: str = "fswebcam"
    fswebcam: FswebcamConfig = Field(default_factory=FswebcamConfig)


class VisionConfig(BaseModel):
    camera: CameraConfig = Field(default_factory=CameraConfig)


class MotionConfig(BaseModel):
    driver: str = "ros2_nav"
    wait_timeout_sec: float = 300.0
    poll_interval_sec: float = 2.0
    arrival_tolerance: float = 150.0

    @field_validator("driver")
    @classmethod
    def driver_must_be_ros2_nav(cls, value: str) -> str:
        if value != "ros2_nav":
            raise ValueError("roamerd motion driver must be ros2_nav")
        return value


class CapabilitiesConfig(BaseModel):
    hearing: HearingConfig = Field(default_factory=HearingConfig)
    speech: SpeechConfig = Field(default_factory=SpeechConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    motion: MotionConfig = Field(default_factory=MotionConfig)


class ControlCompatConfig(BaseModel):
    fallback_to_cli: bool = True


class ControlBridgeConfig(BaseModel):
    enabled: bool = True
    socket: str = "/run/roamer/roamer.sock"
    request_timeout_sec: float = 60.0
    compat: ControlCompatConfig = Field(default_factory=ControlCompatConfig)


class CognitionBridgeConfig(BaseModel):
    enabled: bool = True
    driver: str = "mock"
    endpoint: str = "http://localhost:3000"
    timeout_sec: float = 30.0
    fallback: str | None = None
    local_endpoint: str | None = None
    local_model: str = ""


class DiscordBridgeConfig(BaseModel):
    enabled: bool = False
    channel_id: str = ""
    token_env: str = "DISCORD_BOT_TOKEN"
    source: str = "roamer"
    mention_user_id: str = ""
    mention_role_id: str = ""
    mention: str = ""
    reply_instruction: str = ""


class MemoryBridgeConfig(BaseModel):
    enabled: bool = False
    endpoint: str = "http://localhost:8200"
    timeout_sec: float = 5.0
    buffer_path: str = "/run/roamer/memory-candidates.jsonl"
    max_buffered: int = 1000


class BridgesConfig(BaseModel):
    control: ControlBridgeConfig = Field(default_factory=ControlBridgeConfig)
    cognition: CognitionBridgeConfig = Field(default_factory=CognitionBridgeConfig)
    discord: DiscordBridgeConfig = Field(default_factory=DiscordBridgeConfig)
    memory: MemoryBridgeConfig = Field(default_factory=MemoryBridgeConfig)


class LocalVoicePolicyConfig(BaseModel):
    ignore_wake_while_speaking: bool = True
    stop_phrases: list[str] = Field(default_factory=lambda: ["不用了", "结束", "停止", "可以了"])
    wake_phrases: list[str] = Field(default_factory=lambda: ["Richard", "richard", "理查德"])
    pre_roll_sec: float = 1.0
    followup_timeout_sec: float = 3.0
    continuous_followup_enabled: bool = True
    max_followup_turns: int = 3


class PolicyConfig(BaseModel):
    local_intents: list[LocalIntentRule] = Field(default_factory=list)
    local_voice: LocalVoicePolicyConfig = Field(default_factory=LocalVoicePolicyConfig)
    allow_actions: list[str] = Field(
        default_factory=lambda: [
            "time.now",
            "sense",
            "watch",
            "listen",
            "speak",
            "motion.home",
            "motion.locate",
            "motion.position",
            "motion.status",
            "motion.goto",
            "remind.schedule",
            "emergency_stop",
        ]
    )


class PoseConfig(BaseModel):
    x: float
    y: float
    angle: float | None = None
    frame: str = "valetudo_pixel"


class PlaceConfig(BaseModel):
    pose: PoseConfig
    radius: float = 150.0


class WorldModelConfig(BaseModel):
    places: dict[str, PlaceConfig] = Field(default_factory=dict)
    scene_ttl_sec: float = 300.0


class Ros2ValetudoBridgeConfig(BaseModel):
    host: str = "10.0.0.226"
    port: int = 80
    timeout_sec: float = 8.0


class Ros2Config(BaseModel):
    valetudo_bridge: Ros2ValetudoBridgeConfig = Field(default_factory=Ros2ValetudoBridgeConfig)


class RoamerdConfig(BaseModel):
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    kernel: KernelConfig = Field(default_factory=KernelConfig)
    capabilities: CapabilitiesConfig = Field(default_factory=CapabilitiesConfig)
    bridges: BridgesConfig = Field(default_factory=BridgesConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    world_model: WorldModelConfig = Field(default_factory=WorldModelConfig)
    ros2: Ros2Config = Field(default_factory=Ros2Config)

    @model_validator(mode="after")
    def require_intents_are_allowed(self) -> "RoamerdConfig":
        allowed = set(self.policy.allow_actions)
        for intent in self.policy.local_intents:
            if intent.action not in allowed:
                raise ValueError(
                    f"local intent {intent.name!r} uses disallowed action {intent.action!r}"
                )
        return self


def default_roamerd_config_path() -> Path:
    return Path(__file__).resolve().parents[3] / "config" / "roamerd.yaml"
