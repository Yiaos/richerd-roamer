"""Runtime state manager."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

from roamerd.events.base import Event
from roamerd.events.motion import Position
from roamerd.kernel.event_bus import EventBus


class HealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class AudioState(BaseModel):
    listening: bool = False
    stt_active: bool = False
    playback_active: bool = False
    playback_started_at: datetime | None = None


class MotionState(BaseModel):
    moving: bool = False
    docked: bool | None = None
    battery_percent: int | None = None
    position: Position | None = None


class RuntimeState(BaseModel):
    session_id: str
    started_at: datetime
    mode: str = "idle"
    audio: AudioState = Field(default_factory=AudioState)
    motion: MotionState = Field(default_factory=MotionState)
    modules: dict[str, HealthState] = Field(default_factory=dict)
    bridges: dict[str, HealthState] = Field(default_factory=dict)
    last_interaction_at: datetime | None = None
    cognition_available: bool = True


class StateManager:
    def __init__(self, *, session_id: str, playback_stale_after_sec: float = 120.0) -> None:
        self._state = RuntimeState(
            session_id=session_id,
            started_at=datetime.now(timezone.utc),
        )
        self._playback_stale_after_sec = playback_stale_after_sec

    async def start(self, bus: EventBus) -> None:
        for event_type in (
            "hearing.recording_started",
            "hearing.transcript_ready",
            "hearing.listen_failed",
            "speech.playback_started",
            "speech.playback_completed",
            "speech.playback_failed",
            "motion.started",
            "motion.completed",
            "motion.failed",
            "motion.position_updated",
            "motion.status_updated",
            "system.health_changed",
            "system.module_ready",
            "cognition.unavailable",
            "action.cancelled",
            "action.preempted",
        ):
            bus.subscribe(event_type, self._handle_event)

    def snapshot(self) -> RuntimeState:
        copied = self._state.model_copy(deep=True)
        copied.mode = self._derive_mode()
        return copied

    def get_module_health(self, name: str) -> HealthState:
        return self._state.modules.get(name, HealthState.UNAVAILABLE)

    def get_bridge_health(self, name: str) -> HealthState:
        return self._state.bridges.get(name, HealthState.UNAVAILABLE)

    @property
    def is_speaking(self) -> bool:
        return self._state.audio.playback_active and not self.playback_stale

    @property
    def is_listening(self) -> bool:
        return self._state.audio.listening

    @property
    def is_moving(self) -> bool:
        return self._state.motion.moving

    @property
    def playback_stale(self) -> bool:
        started_at = self._state.audio.playback_started_at
        if not self._state.audio.playback_active or started_at is None:
            return False
        return (
            datetime.now(timezone.utc) - started_at
        ).total_seconds() > self._playback_stale_after_sec

    async def _handle_event(self, event: Event) -> None:
        now = event.occurred_at
        if event.event_type == "hearing.recording_started":
            self._state.audio.listening = True
            self._state.audio.stt_active = True
        elif event.event_type in {"hearing.transcript_ready", "hearing.listen_failed"}:
            self._state.audio.listening = False
            self._state.audio.stt_active = False
            self._state.last_interaction_at = now
        elif event.event_type == "speech.playback_started":
            self._state.audio.playback_active = True
            self._state.audio.playback_started_at = now
        elif event.event_type in {"speech.playback_completed", "speech.playback_failed"}:
            self._state.audio.playback_active = False
        elif event.event_type == "motion.started":
            self._state.motion.moving = True
        elif event.event_type in {"motion.completed", "motion.failed"}:
            self._state.motion.moving = False
        elif event.event_type == "motion.position_updated":
            position = event.payload.get("position")
            if isinstance(position, dict):
                self._state.motion.position = Position.model_validate(position)
        elif event.event_type == "motion.status_updated":
            battery = event.payload.get("battery_percent")
            self._state.motion.battery_percent = int(battery) if isinstance(battery, int) else None
            docked = event.payload.get("docked")
            self._state.motion.docked = docked if isinstance(docked, bool) else None
        elif event.event_type in {"system.health_changed", "system.module_ready"}:
            name = str(event.payload.get("name", ""))
            component_type = str(event.payload.get("component_type", "module"))
            raw_state = str(event.payload.get("state", HealthState.HEALTHY.value))
            state = HealthState(raw_state)
            if component_type == "bridge":
                self._state.bridges[name] = state
            else:
                self._state.modules[name] = state
        elif event.event_type == "cognition.unavailable":
            self._state.cognition_available = False
        elif event.event_type in {"action.cancelled", "action.preempted"}:
            self._clear_action_state(str(event.payload.get("action_type", "")))

    def _derive_mode(self) -> str:
        if any(item == HealthState.UNAVAILABLE for item in self._state.modules.values()):
            return "error"
        if self._state.audio.listening:
            return "listening"
        if self._state.audio.playback_active and not self.playback_stale:
            return "speaking"
        if self._state.motion.moving:
            return "moving"
        return "idle"

    def _clear_action_state(self, action_type: str) -> None:
        if action_type == "listen":
            self._state.audio.listening = False
            self._state.audio.stt_active = False
        elif action_type == "speak":
            self._state.audio.playback_active = False
        elif action_type.startswith("motion."):
            self._state.motion.moving = False
