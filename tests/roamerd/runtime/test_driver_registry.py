import pytest

from roamerd.capabilities.hearing.drivers.mock import MockWakewordDriver
from roamerd.capabilities.hearing.drivers.silero_vad import SileroVadDriver
from roamerd.capabilities.motion.drivers.mock_ros2 import MockRos2NavDriver
from roamerd.capabilities.speech.drivers.edge_tts import EdgeTtsDriver
from roamerd.capabilities.vision.drivers.fswebcam import FswebcamCameraDriver
from roamerd.contracts.exceptions import DriverNotFoundError
from roamerd.runtime.driver_registry import load_driver, registered_drivers


def test_registry_loads_mock_drivers_by_category_and_name() -> None:
    wakeword = load_driver("wakeword", "mock")
    motion = load_driver("motion", "mock_ros2_nav")

    assert isinstance(wakeword, MockWakewordDriver)
    assert isinstance(motion, MockRos2NavDriver)


def test_registry_rejects_unknown_driver() -> None:
    with pytest.raises(DriverNotFoundError):
        load_driver("motion", "missing")


def test_registry_lists_expected_mock_categories() -> None:
    drivers = registered_drivers()

    assert "mock" in drivers["wakeword"]
    assert "mock_ros2_nav" in drivers["motion"]
    assert "mock" in drivers["tts"]


def test_registry_registers_all_implemented_driver_boundaries() -> None:
    drivers = registered_drivers()

    assert set(drivers["audio_capture"]) == {"alsa", "mock"}
    assert set(drivers["vad"]) == {"mock", "silero"}
    assert set(drivers["wakeword"]) == {"mock", "openwakeword", "su03t_gpio"}
    assert set(drivers["realtime_stt"]) == {"mock", "network_asr"}
    assert set(drivers["batch_asr"]) == {"funasr", "mock"}
    assert set(drivers["tts"]) == {"edge_tts", "mock", "piper"}
    assert set(drivers["playback"]) == {"alsa", "mock"}
    assert set(drivers["bluetooth"]) == {"bluez", "mock"}
    assert set(drivers["camera"]) == {"fswebcam", "mock"}
    assert set(drivers["motion"]) == {"mock_ros2_nav", "ros2_nav"}


def test_registry_loads_real_boundaries_with_config() -> None:
    vad = load_driver("vad", "silero", {"model": lambda pcm: 0.2, "threshold": 0.1})
    tts = load_driver("tts", "edge_tts", {"voice": "zh-CN-YunxiNeural"})
    camera = load_driver("camera", "fswebcam", {"device": "/dev/video2"})

    assert isinstance(vad, SileroVadDriver)
    assert isinstance(tts, EdgeTtsDriver)
    assert isinstance(camera, FswebcamCameraDriver)
