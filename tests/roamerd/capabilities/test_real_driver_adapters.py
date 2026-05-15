import asyncio
import json
import sys
import types

from roamerd.app import build_stt_driver
from roamerd.capabilities.hearing.drivers.legacy_batch import ExistingAudioBatchSttDriver
from roamerd.capabilities.hearing.drivers.network_asr import (
    NetworkAsrDriver,
    NetworkThenBatchSttDriver,
)
from roamerd.capabilities.hearing.drivers.wakeword import LegacyWakeDriver, build_wake_driver
from roamerd.capabilities.speech.drivers.legacy import LegacyAlsaPlaybackDriver, LegacyTtsDriver
from roamerd.capabilities.vision.drivers.fswebcam import FswebcamCameraDriver
from roamerd.config.schema import (
    EdgeConfig,
    FswebcamConfig,
    FunAsrConfig,
    HearingConfig,
    PlaybackConfig,
    SttConfig,
    TtsConfig,
    WakewordConfig,
)


def test_existing_audio_batch_stt_wraps_legacy_result(tmp_path, monkeypatch) -> None:
    module = types.ModuleType("roamer.plugins.interaction.drivers.speech.asr.funasr")

    class FakeFunASRDriver:
        def __init__(self, config):
            self.config = config

        def transcribe(self, audio_path):
            return {"ok": True, "text": "你好", "confidence": 0.8}

    module.FunASRDriver = FakeFunASRDriver
    monkeypatch.setitem(sys.modules, "roamer.plugins.interaction.drivers.speech.asr.funasr", module)
    audio = tmp_path / "x.wav"
    audio.write_bytes(b"wav")

    async def scenario():
        return await ExistingAudioBatchSttDriver(FunAsrConfig()).transcribe(str(audio))

    assert asyncio.run(scenario()).text == "你好"


def test_network_asr_driver_streams_audio_to_websocket(tmp_path) -> None:
    audio = tmp_path / "x.pcm"
    audio.write_bytes(b"abcd")
    sent: list[dict[str, object]] = []

    class FakeWebSocket:
        def __init__(self) -> None:
            self.events = [
                json.dumps({"type": "session.created"}),
                json.dumps({"type": "transcription.done", "text": "language zh <asr_text>你好"}),
            ]

        def send(self, payload: str) -> None:
            sent.append(json.loads(payload))

        def recv(self, timeout=None):  # noqa: ANN001 - websocket sync API
            return self.events.pop(0)

        def close(self) -> None:
            return None

    def connect_factory(url, open_timeout, proxy=None):  # noqa: ANN001
        assert url == "ws://asr.example.test/v1/realtime"
        assert open_timeout == 5.0
        return FakeWebSocket()

    async def scenario():
        driver = NetworkAsrDriver(
            url="ws://asr.example.test/v1/realtime",
            model="qwen3-asr-0.6b",
            connect_factory=connect_factory,
        )
        return await driver.transcribe(str(audio), timeout=7.0)

    transcript = asyncio.run(scenario())

    assert transcript.text == "你好"
    assert sent[0] == {"type": "session.update", "model": "qwen3-asr-0.6b"}
    assert sent[1]["type"] == "input_audio_buffer.append"
    assert sent[-1] == {"type": "input_audio_buffer.commit", "final": True}


def test_network_then_batch_stt_driver_falls_back_after_network_error() -> None:
    class FailingNetwork:
        async def transcribe(self, audio_path=None, *, timeout=10.0):  # noqa: ANN001
            raise RuntimeError("network down")

        async def health_check(self):
            from roamerd.kernel.state_manager import HealthState

            return HealthState.DEGRADED

    class BatchFallback:
        async def transcribe(self, audio_path=None, *, timeout=10.0):  # noqa: ANN001
            from roamerd.events.hearing import TranscriptPayload

            return TranscriptPayload(text="fallback", audio_path=audio_path)

        async def health_check(self):
            from roamerd.kernel.state_manager import HealthState

            return HealthState.HEALTHY

    async def scenario():
        driver = NetworkThenBatchSttDriver(primary=FailingNetwork(), fallback=BatchFallback())
        return await driver.transcribe("/tmp/audio.wav")

    assert asyncio.run(scenario()).text == "fallback"


def test_build_stt_driver_uses_network_with_batch_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "roamerd.app.LegacyBatchSttDriver",
        lambda **kwargs: object(),
    )
    config = HearingConfig(
        stt=SttConfig(mode="realtime_with_batch_fallback", provider="vllm_realtime")
    )

    driver = build_stt_driver(config)

    assert isinstance(driver, NetworkThenBatchSttDriver)


def test_legacy_wake_driver_wraps_su03t_hit() -> None:
    class FakeLegacyDriver:
        def __init__(self) -> None:
            self.started = False
            self.stopped = False

        def start(self) -> None:
            self.started = True

        def stop(self) -> None:
            self.stopped = True

        def wait_hit(self, timeout):  # noqa: ANN001
            return True

    async def scenario():
        legacy = FakeLegacyDriver()
        driver = LegacyWakeDriver(source="su03t_gpio", legacy_driver=legacy, phrase="richard")
        await driver.start()
        wake = await driver.wait_for_wake()
        await driver.stop()
        return wake, legacy.started, legacy.stopped

    wake, started, stopped = asyncio.run(scenario())
    assert wake is not None
    assert wake.source == "su03t_gpio"
    assert wake.phrase == "richard"
    assert (started, stopped) == (True, True)


def test_build_wake_driver_keeps_openwakeword_compat() -> None:
    driver = build_wake_driver(WakewordConfig(driver="openwakeword", model="model.onnx"))

    assert isinstance(driver, LegacyWakeDriver)


def test_legacy_tts_wraps_edge_driver(monkeypatch) -> None:
    module = types.ModuleType("roamer.plugins.interaction.drivers.speech.tts.edge")

    class FakeEdgeDriver:
        def __init__(self, config):
            self.config = config

        def synthesize(self, text, output, style=None):
            return {"ok": True, "path": output, "text": text, "style": style}

    module.EdgeDriver = FakeEdgeDriver
    monkeypatch.setitem(sys.modules, "roamer.plugins.interaction.drivers.speech.tts.edge", module)

    async def scenario():
        driver = LegacyTtsDriver(TtsConfig(primary="edge", edge=EdgeConfig()))
        return await driver.synthesize("hi", "/tmp/x.wav", style="cheerful")

    assert asyncio.run(scenario())["ok"] is True


def test_legacy_playback_wraps_alsa_driver(monkeypatch) -> None:
    module = types.ModuleType("roamer.plugins.interaction.drivers.audio.alsa")

    class FakeAlsaDriver:
        def __init__(self, config):
            self.config = config

        def play(self, audio_path):
            return {"ok": True, "played": audio_path}

    module.AlsaDriver = FakeAlsaDriver
    monkeypatch.setitem(sys.modules, "roamer.plugins.interaction.drivers.audio.alsa", module)

    async def scenario():
        return await LegacyAlsaPlaybackDriver(PlaybackConfig()).play("/tmp/x.wav")

    assert asyncio.run(scenario())["played"] == "/tmp/x.wav"


def test_fswebcam_adapter_wraps_legacy_driver(monkeypatch) -> None:
    module = types.ModuleType("roamer.plugins.perception.drivers.camera_fswebcam")

    class FakeFswebcamDriver:
        def __init__(self, config):
            self.config = config

        def snap(self, output, width, height):
            return {"ok": True, "path": output, "width": width, "height": height}

    module.FswebcamDriver = FakeFswebcamDriver
    monkeypatch.setitem(sys.modules, "roamer.plugins.perception.drivers.camera_fswebcam", module)

    async def scenario():
        return await FswebcamCameraDriver(FswebcamConfig(width=320, height=240)).capture()

    assert asyncio.run(scenario())["width"] == 320
