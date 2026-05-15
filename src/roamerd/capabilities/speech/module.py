"""Event-native speech module."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Protocol, runtime_checkable

from roamerd.events.base import Event, make_event
from roamerd.kernel.action_manager import ActionManager
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.state_manager import HealthState


@runtime_checkable
class TtsDriver(Protocol):
    async def synthesize(
        self, text: str, output_path: str, *, style: str | None = None
    ) -> dict[str, object]: ...

    async def health_check(self) -> HealthState: ...


@runtime_checkable
class PlaybackDriver(Protocol):
    async def play(self, audio_path: str, *, device: str = "default") -> dict[str, object]: ...

    async def stop(self) -> None: ...

    async def health_check(self) -> HealthState: ...


@runtime_checkable
class BluetoothDriver(Protocol):
    async def ensure_connected(self) -> bool: ...

    async def disconnect(self) -> None: ...

    async def health_check(self) -> HealthState: ...


class SpeechModule:
    name = "speaker"
    resource = "speaker"
    events_produced = [
        "speech.synthesis_started",
        "speech.playback_started",
        "speech.playback_completed",
        "speech.playback_failed",
        "speech.stopped",
    ]
    events_consumed = [
        "action.started",
        "action.cancelled",
        "action.preempted",
        "speech.stop_requested",
        "system.shutdown_requested",
    ]

    def __init__(
        self,
        *,
        session_id: str,
        action_manager: ActionManager,
        tts_driver: TtsDriver,
        playback_driver: PlaybackDriver,
        bluetooth_driver: BluetoothDriver | None = None,
    ) -> None:
        self._session_id = session_id
        self._actions = action_manager
        self._tts = tts_driver
        self._playback = playback_driver
        self._bluetooth = bluetooth_driver
        self._bus: EventBus | None = None
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def start(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe("action.started", self._on_action_started)
        bus.subscribe("action.cancelled", self._on_action_stopped)
        bus.subscribe("action.preempted", self._on_action_stopped)
        bus.subscribe("speech.stop_requested", self._on_stop_requested)
        bus.subscribe("system.shutdown_requested", self._on_shutdown_requested)
        await bus.publish(
            make_event(
                "system.module_ready",
                source="speech_module",
                session_id=self._session_id,
                payload={"name": self.name, "component_type": "module", "state": "healthy"},
            )
        )

    async def stop(self) -> None:
        await self._playback.stop()
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()

    async def health_check(self) -> HealthState:
        tts = await self._tts.health_check()
        playback = await self._playback.health_check()
        bluetooth = (
            await self._bluetooth.health_check()
            if self._bluetooth is not None
            else HealthState.HEALTHY
        )
        return (
            HealthState.HEALTHY
            if tts == playback == bluetooth == HealthState.HEALTHY
            else HealthState.DEGRADED
        )

    async def _on_action_started(self, event: Event) -> None:
        if event.payload.get("action_type") != "speak" or self._bus is None:
            return
        action_id = event.action_id or ""
        task = asyncio.create_task(self._run_speak(event))
        self._tasks[action_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(action_id, None))

    async def _run_speak(self, event: Event) -> None:
        if self._bus is None:
            return
        payload = event.payload.get("payload")
        args = payload if isinstance(payload, dict) else {}
        text = str(args.get("text", ""))
        style = str(args["style"]) if args.get("style") else None
        save_path = str(args.get("save_path") or f"/tmp/roamerd-{event.action_id or 'speech'}.wav")
        play = bool(args.get("play", True))
        action_id = event.action_id or ""
        await self._bus.publish(
            make_event(
                "speech.synthesis_started",
                source="speech_module",
                session_id=self._session_id,
                action_id=action_id,
                payload={
                    "action_id": action_id,
                    "text_length": len(text),
                    "driver": self._tts.__class__.__name__,
                },
            )
        )
        synth = await self._tts.synthesize(text, save_path, style=style)
        if not synth.get("ok", False):
            await self._actions.fail_action(
                action_id,
                {
                    "error_code": "speech.tts.synthesis_failed",
                    "error_message": str(synth.get("error", "")),
                },
            )
            return
        if not play:
            await self._actions.complete_action(
                action_id, {"text": text, "audio_path": save_path, "played": False}
            )
            return
        if self._bluetooth is not None:
            await self._bluetooth.ensure_connected()
        await self._bus.publish(
            make_event(
                "speech.playback_started",
                source="speech_module",
                session_id=self._session_id,
                action_id=action_id,
                payload={"action_id": action_id, "audio_path": save_path},
            )
        )
        playback = await self._playback.play(save_path)
        if playback.get("ok", False):
            duration_raw = playback.get("duration_sec", 0.0)
            duration = float(duration_raw) if isinstance(duration_raw, (int, float, str)) else 0.0
            await self._bus.publish(
                make_event(
                    "speech.playback_completed",
                    source="speech_module",
                    session_id=self._session_id,
                    action_id=action_id,
                    payload={
                        "action_id": action_id,
                        "audio_path": save_path,
                        "duration_sec": duration,
                    },
                )
            )
            await self._actions.complete_action(
                action_id, {"text": text, "audio_path": save_path, "played": True}
            )
        else:
            await self._bus.publish(
                make_event(
                    "speech.playback_failed",
                    source="speech_module",
                    session_id=self._session_id,
                    action_id=action_id,
                    payload={
                        "error_code": "audio.play.command_failed",
                        "error_message": str(playback.get("error", "")),
                    },
                )
            )
            await self._actions.complete_action(
                action_id,
                {
                    "text": text,
                    "audio_path": save_path,
                    "played": False,
                    "partial": True,
                    "warning_code": "audio.play.command_failed",
                },
            )

    async def _on_stop_requested(self, event: Event) -> None:
        await self._playback.stop()
        await self._stop_active_speech(reason="stop_requested")

    async def _on_shutdown_requested(self, event: Event) -> None:
        await self.stop()

    async def _on_action_stopped(self, event: Event) -> None:
        if event.payload.get("action_type") == "speak":
            await self._playback.stop()
            task = self._tasks.get(event.action_id or "")
            if task is not None:
                task.cancel()

    async def _stop_active_speech(self, *, reason: str) -> None:
        tasks = list(self._tasks.items())
        for _action_id, task in tasks:
            task.cancel()
        for action_id, task in tasks:
            with suppress(asyncio.CancelledError):
                await task
            if self._bus is not None:
                await self._bus.publish(
                    make_event(
                        "speech.stopped",
                        source="speech_module",
                        session_id=self._session_id,
                        action_id=action_id,
                        payload={"action_id": action_id, "reason": reason},
                    )
                )
            action = self._actions.get_action(action_id)
            if action is not None and action.status.value == "running":
                await self._actions.complete_action(
                    action_id,
                    {"played": False, "interrupted": True, "reason": reason},
                )
