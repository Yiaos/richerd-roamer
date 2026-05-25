from __future__ import annotations

import asyncio
from pathlib import Path

from roamerd.capabilities.speech.drivers.bluetooth_base import BluetoothDriver
from roamerd.capabilities.speech.drivers.tts_base import TtsDriver
from roamerd.capabilities.speech.playback import PlaybackDriver
from roamerd.capabilities.speech.playback_state import PlaybackState
from roamerd.events import Event, Priority
from roamerd.kernel import ActionManager, EventBus
from roamerd.types import JSONDict


class SpeechModule:
    name = "speech"
    events_produced = [
        "speech.synthesis_started",
        "speech.playback_started",
        "speech.playback_completed",
        "speech.playback_failed",
    ]
    events_consumed = ["action.started", "action.cancel_requested", "action.preempt_requested"]
    resources = ["speaker"]

    def __init__(
        self,
        *,
        tts: TtsDriver,
        playback: PlaybackDriver,
        bluetooth: BluetoothDriver | None = None,
        action_manager: ActionManager | None = None,
        output_dir: Path,
        session_id: str = "session-1",
        bluetooth_timeout_sec: float = 20.0,
    ) -> None:
        self._tts = tts
        self._playback = playback
        self._bluetooth = bluetooth
        self._actions = action_manager
        self._output_dir = output_dir
        self._session_id = session_id
        self._bluetooth_timeout_sec = bluetooth_timeout_sec
        self._bus: EventBus | None = None
        self._playback_state = PlaybackState()

    async def start(self, bus: EventBus) -> None:
        self._bus = bus
        self._output_dir.mkdir(parents=True, exist_ok=True)
        bus.subscribe("action.started", self._handle_action_started)

    async def stop(self) -> None:
        return None

    async def health_check(self) -> str:
        return "healthy"

    async def _handle_action_started(self, event: Event) -> None:
        if event.payload.get("action_type") != "speech.speak":
            return
        action_id = _str_payload(event.payload, "action_id")
        if action_id is None:
            return
        action = self._actions.get_action(action_id) if self._actions is not None else None
        payload = action.payload if action is not None else {}
        text = _str_payload(payload, "text") or ""
        output_path = self._output_dir / f"{action_id}.wav"
        try:
            await self._publish(
                "speech.synthesis_started",
                {"text_len": len(text), "driver": type(self._tts).__name__},
                action_id=action_id,
                turn_id=event.turn_id,
            )
            synth = await self._tts.synthesize(text, output_path)
            await self._ensure_bluetooth_connected()
            self._playback_state.started()
            await self._publish(
                "speech.playback_started",
                {"path": str(synth.path), "duration_ms": synth.duration_ms},
                action_id=action_id,
                turn_id=event.turn_id,
            )
            await self._playback.play(synth.path)
            self._playback_state.finished()
            await self._publish(
                "speech.playback_completed",
                {"path": str(synth.path), "elapsed_ms": synth.duration_ms},
                action_id=action_id,
                turn_id=event.turn_id,
            )
            if self._actions is not None:
                await self._actions.complete_action(action_id, {"path": str(synth.path)})
        except Exception as exc:
            self._playback_state.finished()
            await self._publish(
                "speech.playback_failed",
                {"error_code": "PLAYBACK_FAILED", "message": str(exc)},
                action_id=action_id,
                turn_id=event.turn_id,
            )
            if self._actions is not None:
                await self._actions.fail_action(
                    action_id,
                    {"error_code": "PLAYBACK_FAILED", "message": str(exc)},
                )

    async def _ensure_bluetooth_connected(self) -> None:
        if self._bluetooth is None:
            return
        if await self._bluetooth.status() == "connected":
            return
        await asyncio.wait_for(self._bluetooth.connect(), timeout=self._bluetooth_timeout_sec)

    async def _publish(
        self,
        event_type: str,
        payload: JSONDict,
        *,
        action_id: str,
        turn_id: str | None,
        priority: Priority = Priority.NORMAL,
    ) -> None:
        if self._bus is None:
            return
        await self._bus.publish(
            Event(
                event_type=event_type,
                source="speech",
                session_id=self._session_id,
                action_id=action_id,
                turn_id=turn_id,
                priority=priority,
                payload=payload,
            )
        )


def _str_payload(payload: JSONDict, key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) else None
