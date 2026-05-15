"""Event-native hearing module."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Protocol, runtime_checkable

from roamerd.events.base import Event, Priority, make_event
from roamerd.events.hearing import EndpointPayload, TranscriptPayload, WakePayload
from roamerd.kernel.action_manager import ActionManager
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.state_manager import HealthState


@runtime_checkable
class SttDriver(Protocol):
    async def transcribe(
        self, audio_path: str | None = None, *, timeout: float = 10.0
    ) -> TranscriptPayload: ...

    async def health_check(self) -> HealthState: ...


@runtime_checkable
class WakeDriver(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def wait_for_wake(self) -> WakePayload | None: ...

    async def health_check(self) -> HealthState: ...


class HearingModule:
    name = "microphone"
    resource = "microphone"
    events_produced = [
        "hearing.wake_triggered",
        "hearing.recording_started",
        "hearing.speech_endpoint_detected",
        "hearing.transcript_ready",
        "hearing.listen_failed",
    ]
    events_consumed = [
        "action.started",
        "action.cancelled",
        "action.preempted",
        "speech.playback_started",
        "speech.playback_completed",
        "system.shutdown_requested",
    ]

    def __init__(
        self,
        *,
        session_id: str,
        action_manager: ActionManager,
        stt_driver: SttDriver,
        wake_driver: WakeDriver | None = None,
    ) -> None:
        self._session_id = session_id
        self._actions = action_manager
        self._stt = stt_driver
        self._wake = wake_driver
        self._bus: EventBus | None = None
        self._stopped = False
        self._wake_suppressed = False
        self._wake_task: asyncio.Task[None] | None = None
        self._listen_tasks: dict[str, asyncio.Task[None]] = {}

    async def start(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe("action.started", self._on_action_started)
        bus.subscribe("action.cancelled", self._on_action_stopped)
        bus.subscribe("action.preempted", self._on_action_stopped)
        bus.subscribe("speech.playback_started", self._on_playback_started)
        bus.subscribe("speech.playback_completed", self._on_playback_completed)
        bus.subscribe("speech.playback_failed", self._on_playback_completed)
        bus.subscribe("system.shutdown_requested", self._on_shutdown_requested)
        if self._wake is not None:
            await self._wake.start()
            self._wake_task = asyncio.create_task(self._wake_loop())
        await bus.publish(
            make_event(
                "system.module_ready",
                source="hearing_module",
                session_id=self._session_id,
                payload={"name": self.name, "component_type": "module", "state": "healthy"},
            )
        )

    async def stop(self) -> None:
        self._stopped = True
        if self._wake_task is not None:
            self._wake_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._wake_task
            self._wake_task = None
        tasks = list(self._listen_tasks.values())
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._listen_tasks.clear()
        if self._wake is not None:
            await self._wake.stop()

    async def health_check(self) -> HealthState:
        stt_health = await self._stt.health_check()
        if self._wake is None:
            return stt_health
        wake_health = await self._wake.health_check()
        if HealthState.UNAVAILABLE in {stt_health, wake_health}:
            return HealthState.UNAVAILABLE
        if HealthState.DEGRADED in {stt_health, wake_health}:
            return HealthState.DEGRADED
        return HealthState.HEALTHY

    async def trigger_wake(
        self, *, phrase: str | None = None, command_text: str | None = None
    ) -> None:
        if self._bus is None:
            return
        await self._bus.publish(
            make_event(
                "hearing.wake_triggered",
                source="hearing_module",
                session_id=self._session_id,
                payload={"source": "manual", "phrase": phrase, "command_text": command_text},
                priority=Priority.HIGH,
            )
        )

    async def _on_action_started(self, event: Event) -> None:
        if event.payload.get("action_type") != "listen":
            return
        if self._bus is None:
            return
        action_id = event.action_id or ""
        task = asyncio.create_task(self._run_listen(event))
        self._listen_tasks[action_id] = task
        task.add_done_callback(lambda _task: self._listen_tasks.pop(action_id, None))

    async def _run_listen(self, event: Event) -> None:
        if self._bus is None:
            return
        action_id = event.action_id or ""
        await self._bus.publish(
            make_event(
                "hearing.recording_started",
                source="hearing_module",
                session_id=self._session_id,
                action_id=action_id,
                payload={"action_id": action_id, "config": event.payload.get("payload", {})},
            )
        )
        try:
            request_payload = event.payload.get("payload")
            audio_path = None
            timeout = 10.0
            if isinstance(request_payload, dict):
                audio = request_payload.get("audio_path")
                audio_path = str(audio) if audio else None
                raw_timeout = request_payload.get("timeout")
                timeout = float(raw_timeout) if isinstance(raw_timeout, (int, float)) else timeout
            transcript = await self._stt.transcribe(audio_path, timeout=timeout)
        except Exception as exc:
            await self._actions.fail_action(
                action_id,
                {"error_code": "hearing.listen_failed", "error_message": str(exc)},
            )
            await self._bus.publish(
                make_event(
                    "hearing.listen_failed",
                    source="hearing_module",
                    session_id=self._session_id,
                    action_id=action_id,
                    payload={"error_code": "hearing.listen_failed", "error_message": str(exc)},
                )
            )
            return
        if transcript.duration_sec is not None:
            await self._bus.publish(
                make_event(
                    "hearing.speech_endpoint_detected",
                    source="hearing_module",
                    session_id=self._session_id,
                    action_id=action_id,
                    payload=EndpointPayload(
                        action_id=action_id,
                        duration_sec=transcript.duration_sec,
                        audio_path=transcript.audio_path,
                    ).model_dump(mode="json"),
                )
            )
        await self._bus.publish(
            make_event(
                "hearing.transcript_ready",
                source="hearing_module",
                session_id=self._session_id,
                action_id=action_id,
                payload=transcript.model_dump(mode="json"),
                priority=Priority.HIGH,
                turn_id=event.turn_id,
            )
        )
        await self._actions.complete_action(action_id, transcript.model_dump(mode="json"))

    async def _on_action_stopped(self, event: Event) -> None:
        if event.payload.get("action_type") != "listen":
            return
        task = self._listen_tasks.get(event.action_id or "")
        if task is not None:
            task.cancel()

    async def _on_playback_started(self, event: Event) -> None:
        self._wake_suppressed = True

    async def _on_playback_completed(self, event: Event) -> None:
        self._wake_suppressed = False

    async def _on_shutdown_requested(self, event: Event) -> None:
        await self.stop()

    async def _wake_loop(self) -> None:
        while not self._stopped and self._bus is not None and self._wake is not None:
            wake = await self._wake.wait_for_wake()
            if wake is None:
                continue
            if self._wake_suppressed and wake.source != "su03t_gpio":
                continue
            await self._bus.publish(
                make_event(
                    "hearing.wake_triggered",
                    source="hearing_module",
                    session_id=self._session_id,
                    payload=wake.model_dump(mode="json"),
                    priority=Priority.HIGH,
                )
            )
