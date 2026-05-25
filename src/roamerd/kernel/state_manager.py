from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from roamerd.events import Event
from roamerd.kernel.event_bus import EventBus


class StateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class Position(StateModel):
    x: float
    y: float
    angle: float | None = None
    frame: str = "valetudo_pixel"


class AudioState(StateModel):
    listening: bool = False
    stt_active: bool = False
    playback_active: bool = False
    playback_started_at: datetime | None = None
    playback_generation: int = 0


class MotionState(StateModel):
    moving: bool = False
    docked: bool | None = None
    battery_percent: int | None = None
    position: Position | None = None


class RuntimeState(StateModel):
    session_id: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    mode: str = "idle"
    audio: AudioState = Field(default_factory=AudioState)
    motion: MotionState = Field(default_factory=MotionState)
    modules: dict[str, HealthState] = Field(default_factory=dict)
    bridges: dict[str, HealthState] = Field(default_factory=dict)
    last_interaction_at: datetime | None = None
    cognition_available: bool = True


class StateManager:
    def __init__(
        self,
        *,
        session_id: str,
        playback_stale_after_sec: float = 120.0,
    ) -> None:
        self._state = RuntimeState(session_id=session_id)
        self._playback_stale_after_sec = playback_stale_after_sec

    async def start(self, bus: EventBus) -> None:
        bus.subscribe_pattern("*", self.apply_event)

    async def apply_event(self, event: Event) -> None:
        if event.event_type == "hearing.recording_started":
            self._state.audio.listening = True
            self._state.audio.stt_active = True
        elif event.event_type == "hearing.transcript_ready":
            self._state.audio.listening = False
            self._state.audio.stt_active = False
            self._state.last_interaction_at = event.occurred_at
        elif event.event_type == "speech.playback_started":
            self._state.audio.playback_active = True
            self._state.audio.playback_started_at = event.occurred_at
            self._state.audio.playback_generation += 1
        elif event.event_type in {"speech.playback_completed", "speech.playback_failed"}:
            self._state.audio.playback_active = False
            self._state.audio.playback_generation += 1
        elif event.event_type == "motion.started":
            self._state.motion.moving = True
        elif event.event_type in {"motion.completed", "motion.failed"}:
            self._state.motion.moving = False
        elif event.event_type == "motion.position_updated":
            self._apply_position(event)
        elif event.event_type == "motion.status_updated":
            self._apply_motion_status(event)
        elif event.event_type == "system.module_ready":
            module = _str_payload(event, "module")
            if module:
                self._state.modules[module] = HealthState.HEALTHY
        elif event.event_type == "system.health_changed":
            self._apply_health(event)
        elif event.event_type == "cognition.unavailable":
            self._state.cognition_available = False
        self._state.mode = self._derive_mode()

    def snapshot(self) -> RuntimeState:
        self._state.mode = self._derive_mode()
        return self._state.model_copy(deep=True)

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
        elapsed = (datetime.now(UTC) - started_at).total_seconds()
        return elapsed > self._playback_stale_after_sec

    @property
    def cognition_available(self) -> bool:
        return self._state.cognition_available

    def _apply_position(self, event: Event) -> None:
        x = _float_payload(event, "x")
        y = _float_payload(event, "y")
        if x is None or y is None:
            return
        self._state.motion.position = Position(
            x=x,
            y=y,
            angle=_float_payload(event, "angle"),
        )

    def _apply_motion_status(self, event: Event) -> None:
        battery = _int_payload(event, "battery_percent")
        if battery is not None:
            self._state.motion.battery_percent = battery
        docked = event.payload.get("docked")
        if isinstance(docked, bool):
            self._state.motion.docked = docked

    def _apply_health(self, event: Event) -> None:
        component = _str_payload(event, "component")
        status = _health_payload(event)
        if component is None or status is None:
            return
        kind = _str_payload(event, "kind")
        if kind == "bridge":
            self._state.bridges[component] = status
        else:
            self._state.modules[component] = status
        if component == "cognition":
            self._state.cognition_available = status is HealthState.HEALTHY

    def _derive_mode(self) -> str:
        if any(health is HealthState.UNAVAILABLE for health in self._state.modules.values()):
            return "error"
        if self._state.audio.listening:
            return "listening"
        if self.is_speaking:
            return "speaking"
        if self._state.motion.moving:
            return "moving"
        return "idle"


def _str_payload(event: Event, key: str) -> str | None:
    value = event.payload.get(key)
    return value if isinstance(value, str) else None


def _float_payload(event: Event, key: str) -> float | None:
    value = event.payload.get(key)
    if isinstance(value, int | float):
        return float(value)
    return None


def _int_payload(event: Event, key: str) -> int | None:
    value = event.payload.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _health_payload(event: Event) -> HealthState | None:
    value = _str_payload(event, "status")
    if value is None:
        return None
    try:
        return HealthState(value)
    except ValueError:
        return None
