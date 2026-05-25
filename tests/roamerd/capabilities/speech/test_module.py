from pathlib import Path

import pytest

from roamerd.capabilities.speech.drivers.bluetooth_base import BluetoothDriver
from roamerd.capabilities.speech.drivers.tts_base import SynthResult, TtsDriver
from roamerd.capabilities.speech.module import SpeechModule
from roamerd.capabilities.speech.playback import PlaybackDriver
from roamerd.events import Event
from roamerd.kernel import ActionManager, ActionRequestError, EventBus, StateManager
from roamerd.kernel.action_manager import ActionStatus


class FakeTtsDriver:
    async def synthesize(self, text: str, output_path: Path) -> SynthResult:
        return SynthResult(path=output_path, duration_ms=len(text) * 10)


class FakePlaybackDriver:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.played: list[Path] = []

    async def play(self, path: Path) -> None:
        self.played.append(path)
        if self.fail:
            raise RuntimeError("speaker unavailable")


class FakeBluetoothDriver:
    def __init__(self, *, fail_connect: bool = False) -> None:
        self.connected = False
        self.fail_connect = fail_connect

    async def status(self) -> str:
        return "connected" if self.connected else "disconnected"

    async def connect(self) -> None:
        if self.fail_connect:
            raise RuntimeError("bluetooth unavailable")
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False


def test_driver_protocols_accept_fake_implementations() -> None:
    tts: TtsDriver = FakeTtsDriver()
    playback: PlaybackDriver = FakePlaybackDriver()
    bluetooth: BluetoothDriver = FakeBluetoothDriver()

    assert tts is not None
    assert playback is not None
    assert bluetooth is not None


@pytest.mark.asyncio
async def test_speech_module_lifecycle_and_contract_declarations(tmp_path: Path) -> None:
    bus = EventBus()
    module = SpeechModule(
        tts=FakeTtsDriver(),
        playback=FakePlaybackDriver(),
        output_dir=tmp_path,
    )

    await module.start(bus)
    await module.stop()

    assert module.name == "speech"
    assert await module.health_check() == "healthy"
    assert "speech.playback_started" in module.events_produced
    assert "action.started" in module.events_consumed


@pytest.mark.asyncio
async def test_speak_action_synthesizes_plays_and_completes_action(tmp_path: Path) -> None:
    bus = EventBus()
    actions = ActionManager()
    state = StateManager(session_id="session-1")
    playback = FakePlaybackDriver()
    bluetooth = FakeBluetoothDriver()
    module = SpeechModule(
        tts=FakeTtsDriver(),
        playback=playback,
        bluetooth=bluetooth,
        action_manager=actions,
        output_dir=tmp_path,
        session_id="session-1",
    )
    speech_events: list[Event] = []

    async def handler(event: Event) -> None:
        speech_events.append(event)

    bus.subscribe_pattern("speech.*", handler)
    await actions.start(bus)
    await state.start(bus)
    await module.start(bus)
    action = await actions.request_action(
        "speech.speak",
        {"text": "你好"},
        resource="speaker",
        source_module="speech",
    )
    assert not isinstance(action, ActionRequestError)

    await bus.run_until_idle()

    assert bluetooth.connected is True
    assert playback.played == [tmp_path / f"{action.action_id}.wav"]
    assert [event.event_type for event in speech_events] == [
        "speech.synthesis_started",
        "speech.playback_started",
        "speech.playback_completed",
    ]
    assert actions.get_action(action.action_id).status is ActionStatus.COMPLETED
    assert state.is_speaking is False


@pytest.mark.asyncio
async def test_playback_failure_fails_action_and_releases_speaker(tmp_path: Path) -> None:
    bus = EventBus()
    actions = ActionManager()
    module = SpeechModule(
        tts=FakeTtsDriver(),
        playback=FakePlaybackDriver(fail=True),
        action_manager=actions,
        output_dir=tmp_path,
        session_id="session-1",
    )
    speech_events: list[Event] = []

    async def handler(event: Event) -> None:
        speech_events.append(event)

    bus.subscribe_pattern("speech.*", handler)
    await actions.start(bus)
    await module.start(bus)
    action = await actions.request_action(
        "speech.speak",
        {"text": "你好"},
        resource="speaker",
        source_module="speech",
    )
    assert not isinstance(action, ActionRequestError)

    await bus.run_until_idle()
    next_action = await actions.request_action("speech.speak", {}, resource="speaker")

    assert actions.get_action(action.action_id).status is ActionStatus.FAILED
    assert speech_events[-1].event_type == "speech.playback_failed"
    assert not isinstance(next_action, ActionRequestError)


@pytest.mark.asyncio
async def test_bluetooth_connect_failure_fails_action_before_playback(tmp_path: Path) -> None:
    bus = EventBus()
    actions = ActionManager()
    playback = FakePlaybackDriver()
    module = SpeechModule(
        tts=FakeTtsDriver(),
        playback=playback,
        bluetooth=FakeBluetoothDriver(fail_connect=True),
        action_manager=actions,
        output_dir=tmp_path,
        session_id="session-1",
        bluetooth_timeout_sec=0.01,
    )
    speech_events: list[Event] = []

    async def handler(event: Event) -> None:
        speech_events.append(event)

    bus.subscribe_pattern("speech.*", handler)
    await actions.start(bus)
    await module.start(bus)
    action = await actions.request_action(
        "speech.speak",
        {"text": "你好"},
        resource="speaker",
        source_module="speech",
    )
    assert not isinstance(action, ActionRequestError)

    await bus.run_until_idle()

    assert playback.played == []
    assert actions.get_action(action.action_id).status is ActionStatus.FAILED
    assert [event.event_type for event in speech_events] == [
        "speech.synthesis_started",
        "speech.playback_failed",
    ]
    assert "bluetooth unavailable" in str(actions.get_action(action.action_id).error)
