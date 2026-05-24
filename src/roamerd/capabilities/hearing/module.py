from __future__ import annotations

import asyncio
from uuid import uuid4

from roamerd.capabilities.hearing.drivers.asr_base import BatchAsrDriver
from roamerd.capabilities.hearing.drivers.audio_capture_base import AudioCaptureDriver
from roamerd.capabilities.hearing.drivers.realtime_stt_base import RealtimeSttDriver
from roamerd.capabilities.hearing.drivers.vad_base import VadDriver
from roamerd.capabilities.hearing.drivers.wakeword_base import WakewordDriver
from roamerd.capabilities.hearing.wake_loop import WakeGate
from roamerd.capabilities.hearing.wake_phrases import strip_wake_phrase
from roamerd.events import Event, Priority
from roamerd.kernel import ActionManager, EventBus, StateManager
from roamerd.kernel.action_manager import ActionStatus
from roamerd.types import JSONDict


class HearingModule:
    name = "hearing"
    events_produced = [
        "hearing.wake_triggered",
        "hearing.recording_started",
        "hearing.speech_endpoint_detected",
        "hearing.transcript_ready",
        "hearing.listen_failed",
    ]
    events_consumed = [
        "system.startup",
        "speech.playback_started",
        "speech.playback_completed",
        "speech.playback_failed",
    ]
    resources = ["microphone"]

    def __init__(
        self,
        *,
        wakeword: WakewordDriver,
        capture: AudioCaptureDriver,
        vad: VadDriver,
        realtime_stt: RealtimeSttDriver,
        batch_asr: BatchAsrDriver | None = None,
        state: StateManager | None = None,
        action_manager: ActionManager | None = None,
        session_id: str = "session-1",
        wake_phrases: list[str] | None = None,
    ) -> None:
        self._wakeword = wakeword
        self._capture = capture
        self._vad = vad
        self._realtime_stt = realtime_stt
        self._batch_asr = batch_asr
        self._state = state
        self._actions = action_manager
        self._session_id = session_id
        self._wake_phrases = wake_phrases or []
        self._bus: EventBus | None = None
        self._wake_task: asyncio.Task[None] | None = None
        self._listen_tasks: dict[str, asyncio.Task[None]] = {}
        self._wake_gate = WakeGate(state)
        self._stopped = True

    async def start(self, bus: EventBus) -> None:
        self._bus = bus
        self._stopped = False
        bus.subscribe("speech.playback_started", self._handle_playback_event)
        bus.subscribe("speech.playback_completed", self._handle_playback_event)
        bus.subscribe("speech.playback_failed", self._handle_playback_event)
        bus.subscribe("action.started", self._handle_action_started)
        bus.subscribe("action.cancel_requested", self._handle_action_stop_requested)
        bus.subscribe("action.preempt_requested", self._handle_action_stop_requested)
        self._wake_task = asyncio.create_task(self._wake_loop())

    async def stop(self) -> None:
        self._stopped = True
        if self._wake_task is not None:
            self._wake_task.cancel()
            try:
                await self._wake_task
            except asyncio.CancelledError:
                pass
            self._wake_task = None
        for task in self._listen_tasks.values():
            task.cancel()
        for task in list(self._listen_tasks.values()):
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._listen_tasks.clear()

    async def health_check(self) -> str:
        return "healthy"

    async def _handle_playback_event(self, event: Event) -> None:
        if event.event_type == "speech.playback_started":
            self._wake_gate.playback_started()
        elif event.event_type in {"speech.playback_completed", "speech.playback_failed"}:
            self._wake_gate.playback_finished()

    async def _handle_action_started(self, event: Event) -> None:
        if event.payload.get("action_type") != "hearing.listen" or event.action_id is None:
            return
        self._listen_tasks[event.action_id] = asyncio.create_task(
            self._run_listen_action(event.action_id, event.turn_id or event.action_id)
        )

    async def _handle_action_stop_requested(self, event: Event) -> None:
        if event.action_id is None:
            return
        task = self._listen_tasks.pop(event.action_id, None)
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        if self._actions is not None:
            await self._actions.mark_cancelled(event.action_id, "listen_cancelled")

    async def _run_listen_action(self, action_id: str, turn_id: str) -> None:
        try:
            await self._listen_once(turn_id, action_id=action_id)
            if self._actions is not None and self._action_still_running(action_id):
                await self._actions.complete_action(action_id, {"ok": True})
        except asyncio.CancelledError:
            raise
        finally:
            self._listen_tasks.pop(action_id, None)

    async def _wake_loop(self) -> None:
        while not self._stopped:
            wake = await self._wakeword.wait_for_wake()
            if self._should_ignore_wake():
                continue
            turn_id = uuid4().hex[:12]
            await self._publish(
                "hearing.wake_triggered",
                {
                    "wakeword": wake.wakeword,
                    "confidence": wake.confidence,
                    "follow_up": wake.follow_up,
                },
                turn_id=turn_id,
                priority=Priority.HIGH,
            )
            await self._listen_once(turn_id)

    async def _listen_once(self, turn_id: str, *, action_id: str | None = None) -> None:
        try:
            await self._publish(
                "hearing.recording_started",
                {"device": "mock", "sample_rate": 16000, "channels": 1},
                turn_id=turn_id,
                action_id=action_id,
                priority=Priority.HIGH,
            )
            pcm = await self._capture.record()
            if not await self._vad.is_speech(pcm):
                await self._publish(
                    "hearing.listen_failed",
                    {"error_code": "NO_SPEECH", "message": "no speech detected"},
                    turn_id=turn_id,
                    action_id=action_id,
                    priority=Priority.HIGH,
                )
                return
            await self._publish(
                "hearing.speech_endpoint_detected",
                {"audio_path": None, "duration_ms": 0, "speech_ms": 0},
                turn_id=turn_id,
                action_id=action_id,
                priority=Priority.HIGH,
            )
            text = await self._transcribe(pcm)
            if action_id is not None and not self._action_still_running(action_id):
                return
            text = strip_wake_phrase(text, self._wake_phrases)
            await self._publish(
                "hearing.transcript_ready",
                {
                    "text": text,
                    "confidence": None,
                    "follow_up_eligible": True,
                    "fallback_eligible": True,
                },
                turn_id=turn_id,
                action_id=action_id,
                priority=Priority.HIGH,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._publish(
                "hearing.listen_failed",
                {"error_code": "LISTEN_FAILED", "message": str(exc)},
                turn_id=turn_id,
                action_id=action_id,
                priority=Priority.HIGH,
            )

    async def _transcribe(self, pcm: bytes) -> str:
        try:
            return await self._realtime_stt.transcribe(pcm)
        except Exception:
            if self._batch_asr is None:
                raise
            return await self._batch_asr.transcribe(pcm)

    def _should_ignore_wake(self) -> bool:
        return self._wake_gate.should_ignore_wake()

    def _action_still_running(self, action_id: str) -> bool:
        if self._actions is None:
            return True
        action = self._actions.get_action(action_id)
        return action is not None and action.status is ActionStatus.RUNNING

    async def _publish(
        self,
        event_type: str,
        payload: JSONDict,
        *,
        turn_id: str,
        action_id: str | None = None,
        priority: Priority = Priority.NORMAL,
    ) -> None:
        if self._bus is None:
            return
        await self._bus.publish(
            Event(
                event_type=event_type,
                source="hearing",
                session_id=self._session_id,
                turn_id=turn_id,
                action_id=action_id,
                priority=priority,
                payload=payload,
            )
        )
