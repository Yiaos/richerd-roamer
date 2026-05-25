import asyncio
from pathlib import Path

import pytest

from roamerd.capabilities.hearing.drivers.wakeword_base import WakeEvent
from roamerd.capabilities.hearing.module import HearingModule
from roamerd.capabilities.speech.drivers.tts_base import SynthResult
from roamerd.capabilities.speech.module import SpeechModule
from roamerd.events import Event
from roamerd.kernel import ActionManager, ActionRequestError, EventBus, StateManager


class QueuedWakeword:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[WakeEvent] = asyncio.Queue()

    async def wait_for_wake(self) -> WakeEvent:
        return await self.queue.get()


class StaticCapture:
    async def record(self) -> bytes:
        return b"hello"


class SpeechVad:
    async def is_speech(self, pcm: bytes) -> bool:
        return True


class StaticStt:
    async def transcribe(self, pcm: bytes) -> str:
        return "现在几点"


class StaticTts:
    async def synthesize(self, text: str, output_path: Path) -> SynthResult:
        return SynthResult(path=output_path, duration_ms=100)


class RecordingPlayback:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    async def play(self, path: Path) -> None:
        self.paths.append(path)


@pytest.mark.asyncio
async def test_mock_wake_to_transcript_to_speak_flow(tmp_path: Path) -> None:
    bus = EventBus()
    state = StateManager(session_id="session-1")
    actions = ActionManager()
    wakeword = QueuedWakeword()
    playback = RecordingPlayback()
    hearing = HearingModule(
        wakeword=wakeword,
        capture=StaticCapture(),
        vad=SpeechVad(),
        realtime_stt=StaticStt(),
        state=state,
        session_id="session-1",
    )
    speech = SpeechModule(
        tts=StaticTts(),
        playback=playback,
        action_manager=actions,
        output_dir=tmp_path,
        session_id="session-1",
    )
    events: list[Event] = []

    async def handler(event: Event) -> None:
        events.append(event)

    bus.subscribe_pattern("*", handler)
    await state.start(bus)
    await actions.start(bus)
    await hearing.start(bus)
    await speech.start(bus)
    runner = asyncio.create_task(bus.run())

    await wakeword.queue.put(WakeEvent(wakeword="小乐小乐", confidence=1.0))
    while not any(event.event_type == "hearing.transcript_ready" for event in events):
        await asyncio.sleep(0.01)

    action = await actions.request_action(
        "speech.speak",
        {"text": "现在是十点"},
        resource="speaker",
        source_module="speech",
    )
    assert not isinstance(action, ActionRequestError)
    while not any(event.event_type == "speech.playback_completed" for event in events):
        await asyncio.sleep(0.01)

    await hearing.stop()
    await speech.stop()
    await bus.stop()
    await runner

    assert action.action_id in {event.action_id for event in events}
    assert [event.event_type for event in events if event.event_type.startswith("hearing.")] == [
        "hearing.wake_triggered",
        "hearing.recording_started",
        "hearing.speech_endpoint_detected",
        "hearing.transcript_ready",
    ]
    assert [event.event_type for event in events if event.event_type.startswith("speech.")] == [
        "speech.synthesis_started",
        "speech.playback_started",
        "speech.playback_completed",
    ]
    assert playback.paths == [tmp_path / f"{action.action_id}.wav"]
