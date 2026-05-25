from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from roamerd.contracts.local_intent import IntentConfig
from roamerd.events import Priority


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartupConfig(StrictModel):
    connect_speaker_on_startup: bool = False
    configure_proxy_on_startup: bool = False
    ensure_control_bridge_on_startup: bool = False
    control_bridge_start_timeout_sec: float = 10.0
    proxy_init_script: str = "scripts/init-roamer-proxy.sh"
    proxy_init_timeout_sec: float = 20.0
    bluetooth_controller_ready_timeout_sec: float = 20.0
    bluetooth_connect_retry_timeout_sec: float = 20.0
    bluetooth_retry_interval_sec: float = 1.0


class SupervisorConfig(StrictModel):
    startup: StartupConfig = Field(default_factory=StartupConfig)


class RuntimeConfig(StrictModel):
    state_dir: str = "/run/roamer"
    playback_stale_after_sec: float = 120.0
    supervisor: SupervisorConfig = Field(default_factory=SupervisorConfig)


class EventBusConfig(StrictModel):
    high_maxsize: int = 1024
    normal_maxsize: int = 1024
    low_maxsize: int = 256
    handler_timeout_sec: float = 5.0
    critical_fast_path_after_sec: float = 0.1


class KernelConfig(StrictModel):
    event_bus: EventBusConfig = Field(default_factory=EventBusConfig)


class DriverConfig(StrictModel):
    driver: str = "mock"


class AlsaConfig(StrictModel):
    capture_device: str = "mock"
    playback_device: str = "mock"
    sample_rate: int = 16000
    channels: int = 1


class SileroConfig(StrictModel):
    model: str = ""
    threshold: float = 0.1


class VadConfig(StrictModel):
    driver: str = "mock"
    silero: SileroConfig = Field(default_factory=SileroConfig)


class SttConfig(StrictModel):
    mode: str = "mock"
    provider: str = "mock"
    url: str = ""
    model: str = ""
    chunk_duration_sec: float = 0.1
    response_timeout_sec: float = 20.0
    fallback: str = "batch"
    batch_driver: str = "mock"


class WakewordConfig(StrictModel):
    enabled: bool = True
    driver: str = "mock"
    model: str = ""
    threshold: float = 0.5
    gpio_chip: str = "gpiochip0"
    gpio_line: int = 17
    edge: str = "rising"
    pull: str = "down"
    debounce_ms: int = 300
    min_interval_sec: float = 1.5
    pre_roll_sec: float = 1.0
    ignore_while_speaking: bool = True
    prompt_sound: bool = False
    phrases: list[str] = Field(default_factory=list)
    followup_timeout_sec: float = 3.0
    continuous_followup_enabled: bool = True
    max_followup_turns: int = 3
    stop_phrases: list[str] = Field(default_factory=list)


class HearingSessionConfig(StrictModel):
    enabled: bool = True
    silence_timeout: float = 2.5
    max_turns: int = 1
    no_sound_default: bool = False


class EndpointConfig(StrictModel):
    mode: str = "vad_endpoint"
    silence_sec: float = 1.5
    min_speech_sec: float = 0.2
    max_record_sec: float = 10.0
    pre_speech_padding_sec: float = 0.3


class HearingConfig(StrictModel):
    audio: DriverConfig = Field(default_factory=DriverConfig)
    alsa: AlsaConfig = Field(default_factory=AlsaConfig)
    vad: VadConfig = Field(default_factory=VadConfig)
    stt: SttConfig = Field(default_factory=SttConfig)
    wakeword: WakewordConfig = Field(default_factory=WakewordConfig)
    session: HearingSessionConfig = Field(default_factory=HearingSessionConfig)
    endpoint: EndpointConfig = Field(default_factory=EndpointConfig)


class TtsConfig(StrictModel):
    primary: str = "mock"
    edge_voice: str = "zh-CN-YunxiNeural"
    piper_binary: str = ""
    piper_model: str = ""


class BluetoothConfig(StrictModel):
    driver: str = "mock"
    speaker_mac: str | None = None


class SpeechConfig(StrictModel):
    playback: DriverConfig = Field(default_factory=DriverConfig)
    alsa: AlsaConfig = Field(default_factory=AlsaConfig)
    tts: TtsConfig = Field(default_factory=TtsConfig)
    bluetooth: BluetoothConfig = Field(default_factory=BluetoothConfig)


class CameraConfig(StrictModel):
    driver: str = "mock"
    device: str = "/dev/video0"
    width: int = 1280
    height: int = 720


class VisionConfig(StrictModel):
    camera: CameraConfig = Field(default_factory=CameraConfig)


class MotionConfig(StrictModel):
    driver: str = "mock_ros2_nav"
    wait_timeout_sec: float = 300.0
    poll_interval_sec: float = 2.0
    arrival_tolerance: float = 150.0


class CapabilitiesConfig(StrictModel):
    hearing: HearingConfig = Field(default_factory=HearingConfig)
    speech: SpeechConfig = Field(default_factory=SpeechConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    motion: MotionConfig = Field(default_factory=MotionConfig)


class ControlBridgeConfig(StrictModel):
    enabled: bool = False
    socket: str = "/run/roamer/roamer.sock"
    request_timeout_sec: float = 60.0
    fallback_to_cli: bool = True


class CognitionBridgeConfig(StrictModel):
    driver: str = "mock"


class TelegramBridgeConfig(StrictModel):
    enabled: bool = False
    channel_id: str = ""
    token_env: str = "ROAMERD_TELEGRAM_BOT_TOKEN"


class BridgesConfig(StrictModel):
    control: ControlBridgeConfig = Field(default_factory=ControlBridgeConfig)
    cognition: CognitionBridgeConfig = Field(default_factory=CognitionBridgeConfig)
    telegram: TelegramBridgeConfig = Field(default_factory=TelegramBridgeConfig)


class PlaceConfig(StrictModel):
    x: float
    y: float
    angle: float | None = None


class WorldModelConfig(StrictModel):
    places: dict[str, PlaceConfig] = Field(default_factory=dict)


class ValetudoBridgeConfig(StrictModel):
    host: str = ""
    port: int = 80
    timeout_sec: float = 8.0


class Ros2Config(StrictModel):
    valetudo_bridge: ValetudoBridgeConfig = Field(default_factory=ValetudoBridgeConfig)


class PolicyConfig(StrictModel):
    local_intents: list[IntentConfig] = Field(default_factory=lambda: _default_intents())


class LoggingConfig(StrictModel):
    enabled: bool = True
    level: str = "INFO"
    dir: str = "logs"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 10
    retention_days: int = 3
    log_transcripts: bool = True
    log_audio_paths: bool = False


class RoamerdConfig(StrictModel):
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    kernel: KernelConfig = Field(default_factory=KernelConfig)
    capabilities: CapabilitiesConfig = Field(default_factory=CapabilitiesConfig)
    bridges: BridgesConfig = Field(default_factory=BridgesConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    world_model: WorldModelConfig = Field(default_factory=WorldModelConfig)
    ros2: Ros2Config = Field(default_factory=Ros2Config)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def _default_intents() -> list[IntentConfig]:
    return [
        IntentConfig(
            name="emergency_stop",
            action="emergency_stop",
            patterns=["停", "别动", "stop"],
            priority=Priority.CRITICAL,
        ),
        IntentConfig(
            name="go_home",
            action="motion.home",
            patterns=["回家", "回充电", "回去充电"],
            priority=Priority.HIGH,
        ),
        IntentConfig(name="time_now", action="time.now", patterns=["现在几点", "几点了"]),
        IntentConfig(name="sense", action="sense", patterns=["你在哪", "状态"]),
        IntentConfig(name="watch", action="watch", patterns=["看一下", "拍张照"]),
        IntentConfig(
            name="position",
            action="motion.position",
            patterns=["你在哪个位置", "当前位置"],
        ),
    ]
