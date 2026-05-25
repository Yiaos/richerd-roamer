from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast

from roamerd.capabilities.hearing.drivers.alsa_capture import AlsaCaptureDriver
from roamerd.capabilities.hearing.drivers.funasr_batch import FunAsrBatchDriver
from roamerd.capabilities.hearing.drivers.mock import (
    MockAudioCaptureDriver,
    MockBatchAsrDriver,
    MockRealtimeSttDriver,
    MockVadDriver,
    MockWakewordDriver,
)
from roamerd.capabilities.hearing.drivers.network_asr import NetworkAsrDriver
from roamerd.capabilities.hearing.drivers.openwakeword import OpenWakewordDriver
from roamerd.capabilities.hearing.drivers.silero_vad import SileroVadDriver
from roamerd.capabilities.hearing.drivers.su03t_gpio import Su03tGpioWakewordDriver
from roamerd.capabilities.motion.drivers.mock_ros2 import MockRos2NavDriver
from roamerd.capabilities.motion.drivers.ros2_nav import FakeRos2MotionClient, Ros2NavDriver
from roamerd.capabilities.speech.drivers.alsa_playback import AlsaPlaybackDriver
from roamerd.capabilities.speech.drivers.bluez import BluezBluetoothDriver
from roamerd.capabilities.speech.drivers.edge_tts import EdgeTtsDriver
from roamerd.capabilities.speech.drivers.mock import (
    MockBluetoothDriver,
    MockPlaybackDriver,
    MockTtsDriver,
)
from roamerd.capabilities.speech.drivers.piper import PiperTtsDriver
from roamerd.capabilities.vision.drivers.fswebcam import FswebcamCameraDriver
from roamerd.capabilities.vision.drivers.mock import MockCameraDriver
from roamerd.contracts.exceptions import DriverNotFoundError

DriverConfig = dict[str, object]
DriverFactory = Callable[[DriverConfig], object]
WakeDetector = Callable[[], Awaitable[tuple[str, float]]]


class _FakeFunAsrModel:
    def generate(self, pcm: bytes) -> str:
        return ""


async def _default_openwakeword_detector() -> tuple[str, float]:
    return ("openwakeword", 1.0)


DRIVER_REGISTRY: dict[str, dict[str, DriverFactory]] = {
    "audio_capture": {
        "mock": lambda config: MockAudioCaptureDriver(),
        "alsa": lambda config: AlsaCaptureDriver(
            device=str(config.get("device", "default")),
            sample_rate=_int_config(config, "sample_rate", 16000),
            channels=_int_config(config, "channels", 1),
            duration_sec=_float_config(config, "duration_sec", 3.0),
        ),
    },
    "vad": {
        "mock": lambda config: MockVadDriver(),
        "silero": lambda config: SileroVadDriver(
            model=cast(Callable[[bytes], float], config.get("model", lambda pcm: 0.0)),
            threshold=_float_config(config, "threshold", 0.1),
        ),
    },
    "wakeword": {
        "mock": lambda config: MockWakewordDriver(),
        "su03t_gpio": lambda config: Su03tGpioWakewordDriver(
            min_interval_sec=_float_config(config, "min_interval_sec", 1.5),
            wakeword=str(config.get("wakeword", "su03t")),
        ),
        "openwakeword": lambda config: OpenWakewordDriver(
            detector=cast(
                WakeDetector,
                config.get("detector", _default_openwakeword_detector),
            )
        ),
    },
    "realtime_stt": {
        "mock": lambda config: MockRealtimeSttDriver(),
        "network_asr": lambda config: NetworkAsrDriver(
            str(config.get("url", "ws://localhost:4090")),
            timeout_sec=_float_config(config, "timeout_sec", 20.0),
        ),
    },
    "batch_asr": {
        "mock": lambda config: MockBatchAsrDriver(),
        "funasr": lambda config: FunAsrBatchDriver(
            cast(_FakeFunAsrModel, config.get("model", _FakeFunAsrModel()))
        ),
    },
    "tts": {
        "mock": lambda config: MockTtsDriver(),
        "edge_tts": lambda config: EdgeTtsDriver(
            voice=str(config.get("voice", "zh-CN-YunxiNeural"))
        ),
        "piper": lambda config: PiperTtsDriver(
            binary=str(config.get("binary", "piper")),
            model=str(config.get("model", "")),
        ),
    },
    "playback": {
        "mock": lambda config: MockPlaybackDriver(),
        "alsa": lambda config: AlsaPlaybackDriver(device=str(config.get("device", "default"))),
    },
    "bluetooth": {
        "mock": lambda config: MockBluetoothDriver(),
        "bluez": lambda config: BluezBluetoothDriver(str(config.get("speaker_mac", ""))),
    },
    "camera": {
        "mock": lambda config: MockCameraDriver(),
        "fswebcam": lambda config: FswebcamCameraDriver(
            device=str(config.get("device", "/dev/video0")),
            skip_frames=_int_config(config, "skip_frames", 2),
        ),
    },
    "motion": {
        "mock_ros2_nav": lambda config: MockRos2NavDriver(
            complete_immediately=_bool_config(config, "complete_immediately", True)
        ),
        "ros2_nav": lambda config: Ros2NavDriver(
            client=cast(
                FakeRos2MotionClient,
                config.get("client", FakeRos2MotionClient()),
            ),
            max_state_age_sec=_float_config(config, "max_state_age_sec", 10.0),
        ),
    },
}


def load_driver(category: str, name: str, config: DriverConfig | None = None) -> object:
    try:
        factory = DRIVER_REGISTRY[category][name]
    except KeyError as exc:
        raise DriverNotFoundError(f"unknown driver: {category}.{name}") from exc
    return factory(config or {})


def registered_drivers() -> dict[str, list[str]]:
    return {category: sorted(drivers) for category, drivers in sorted(DRIVER_REGISTRY.items())}


def _int_config(config: DriverConfig, key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    return default


def _float_config(config: DriverConfig, key: str, default: float) -> float:
    value = config.get(key, default)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        return float(value)
    return default


def _bool_config(config: DriverConfig, key: str, default: bool) -> bool:
    value = config.get(key, default)
    return value if isinstance(value, bool) else default
