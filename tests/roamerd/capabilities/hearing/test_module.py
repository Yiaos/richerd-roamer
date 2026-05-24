import asyncio

import pytest

from roamerd.capabilities.hearing.drivers.audio_capture_base import AudioCaptureDriver
from roamerd.capabilities.hearing.drivers.realtime_stt_base import RealtimeSttDriver
from roamerd.capabilities.hearing.drivers.vad_base import VadDriver
from roamerd.capabilities.hearing.drivers.wakeword_base import WakeEvent, WakewordDriver
from roamerd.capabilities.hearing.module import HearingModule
from roamerd.events import Event
from roamerd.kernel import ActionManager, ActionRequestError, EventBus, StateManager
from roamerd.kernel.action_manager import ActionStatus


class FakeWakewordDriver:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[WakeEvent] = asyncio.Queue()

    async def wait_for_wake(self) -> WakeEvent:
        return await self._queue.get()

    async def emit(self, wakeword: str = "小乐小乐") -> None:
        await self._queue.put(WakeEvent(wakeword=wakeword, confidence=0.95))


class FakeCaptureDriver:
    def __init__(self, pcm: bytes = b"pcm") -> None:
        self.pcm = pcm
        self.cancelled = False

    async def record(self) -> bytes:
        return self.pcm


class BlockingCaptureDriver:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = False

    async def record(self) -> bytes:
        self.started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class FakeVadDriver:
    def __init__(self, speech: bool = True) -> None:
        self.speech = speech

    async def is_speech(self, pcm: bytes) -> bool:
        return self.speech


class FakeRealtimeSttDriver:
    def __init__(self, text: str = "现在几点", *, fail: bool = False) -> None:
        self.text = text
        self.fail = fail

    async def transcribe(self, pcm: bytes) -> str:
        if self.fail:
            raise RuntimeError("realtime unavailable")
        return self.text


class FakeBatchAsrDriver:
    async def transcribe(self, pcm: bytes) -> str:
        return "批处理文本"


def test_driver_protocols_accept_fake_implementations() -> None:
    wakeword: WakewordDriver = FakeWakewordDriver()
    capture: AudioCaptureDriver = FakeCaptureDriver()
    vad: VadDriver = FakeVadDriver()
    stt: RealtimeSttDriver = FakeRealtimeSttDriver()

    assert wakeword is not None
    assert capture is not None
    assert vad is not None
    assert stt is not None


@pytest.mark.asyncio
async def test_hearing_module_lifecycle_and_contract_declarations() -> None:
    module = HearingModule(
        wakeword=FakeWakewordDriver(),
        capture=FakeCaptureDriver(),
        vad=FakeVadDriver(),
        realtime_stt=FakeRealtimeSttDriver(),
    )
    bus = EventBus()

    await module.start(bus)
    await module.stop()

    assert module.name == "hearing"
    assert await module.health_check() == "healthy"
    assert "hearing.wake_triggered" in module.events_produced
    assert "hearing.transcript_ready" in module.events_produced
    assert "system.startup" in module.events_consumed
    assert "speech.playback_started" in module.events_consumed


@pytest.mark.asyncio
async def test_wake_records_and_publishes_transcript_ready() -> None:
    wakeword = FakeWakewordDriver()
    bus = EventBus()
    state = StateManager(session_id="session-1")
    module = HearingModule(
        wakeword=wakeword,
        capture=FakeCaptureDriver(),
        vad=FakeVadDriver(),
        realtime_stt=FakeRealtimeSttDriver("小乐小乐回充电"),
        state=state,
        session_id="session-1",
        wake_phrases=["小乐小乐"],
    )
    events: list[Event] = []

    async def handler(event: Event) -> None:
        events.append(event)

    bus.subscribe_pattern("hearing.*", handler)
    await state.start(bus)
    await module.start(bus)
    runner = asyncio.create_task(bus.run())

    await wakeword.emit()
    while not any(event.event_type == "hearing.transcript_ready" for event in events):
        await asyncio.sleep(0.01)

    await module.stop()
    await bus.stop()
    await runner

    assert [event.event_type for event in events] == [
        "hearing.wake_triggered",
        "hearing.recording_started",
        "hearing.speech_endpoint_detected",
        "hearing.transcript_ready",
    ]
    transcript = events[-1]
    assert transcript.payload["text"] == "回充电"
    assert transcript.payload["follow_up_eligible"] is True
    assert transcript.payload["fallback_eligible"] is True


@pytest.mark.asyncio
async def test_hearing_ignores_wake_while_state_manager_reports_speaking() -> None:
    wakeword = FakeWakewordDriver()
    bus = EventBus()
    state = StateManager(session_id="session-1")
    module = HearingModule(
        wakeword=wakeword,
        capture=FakeCaptureDriver(),
        vad=FakeVadDriver(),
        realtime_stt=FakeRealtimeSttDriver(),
        state=state,
        session_id="session-1",
    )
    events: list[Event] = []

    async def handler(event: Event) -> None:
        events.append(event)

    bus.subscribe_pattern("hearing.*", handler)
    await state.start(bus)
    await module.start(bus)
    runner = asyncio.create_task(bus.run())
    await bus.publish(
        Event(
            event_type="speech.playback_started",
            source="test",
            session_id="session-1",
            payload={"path": "/tmp/out.wav"},
        )
    )
    while not state.is_speaking:
        await asyncio.sleep(0.01)

    await wakeword.emit()
    await asyncio.sleep(0.05)

    await module.stop()
    await bus.stop()
    await runner

    assert events == []


@pytest.mark.asyncio
async def test_realtime_stt_failure_falls_back_to_batch_asr() -> None:
    wakeword = FakeWakewordDriver()
    bus = EventBus()
    module = HearingModule(
        wakeword=wakeword,
        capture=FakeCaptureDriver(),
        vad=FakeVadDriver(),
        realtime_stt=FakeRealtimeSttDriver(fail=True),
        batch_asr=FakeBatchAsrDriver(),
        session_id="session-1",
    )
    transcripts: list[Event] = []

    async def handler(event: Event) -> None:
        transcripts.append(event)

    bus.subscribe("hearing.transcript_ready", handler)
    await module.start(bus)
    runner = asyncio.create_task(bus.run())

    await wakeword.emit()
    while not transcripts:
        await asyncio.sleep(0.01)

    await module.stop()
    await bus.stop()
    await runner

    assert transcripts[0].payload["text"] == "批处理文本"


@pytest.mark.asyncio
async def test_listen_action_can_be_cancelled_without_transcript_or_fallback() -> None:
    bus = EventBus()
    actions = ActionManager(preemption_timeout_sec=0.01)
    capture = BlockingCaptureDriver()
    module = HearingModule(
        wakeword=FakeWakewordDriver(),
        capture=capture,
        vad=FakeVadDriver(),
        realtime_stt=FakeRealtimeSttDriver(fail=True),
        batch_asr=FakeBatchAsrDriver(),
        action_manager=actions,
        session_id="session-1",
    )
    transcripts: list[Event] = []

    async def transcript_handler(event: Event) -> None:
        transcripts.append(event)

    bus.subscribe("hearing.transcript_ready", transcript_handler)
    await actions.start(bus)
    await module.start(bus)
    runner = asyncio.create_task(bus.run())
    action = await actions.request_action(
        "hearing.listen",
        {},
        resource="microphone",
        source_module="hearing",
    )
    assert not isinstance(action, ActionRequestError)
    await asyncio.wait_for(capture.started.wait(), timeout=0.5)

    await actions.cancel_action(action.action_id, "test_cancel")
    while actions.get_action(action.action_id).status is not ActionStatus.CANCELLED:
        await asyncio.sleep(0.01)

    await module.stop()
    await bus.stop()
    await runner

    assert capture.cancelled is True
    assert transcripts == []
    assert actions.get_action(action.action_id).status is ActionStatus.CANCELLED
