from __future__ import annotations

from datetime import UTC, datetime
from math import hypot
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from roamerd.config.schema import PlaceConfig
from roamerd.events import Event
from roamerd.kernel.event_bus import EventBus


class WorldModelBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Position(WorldModelBase):
    x: float
    y: float
    angle: float | None = None
    frame: str = "valetudo_pixel"
    room: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Place(WorldModelBase):
    name: str
    center: tuple[float, float]
    radius: float = 250.0
    angle: float | None = None
    frame: str = "valetudo_pixel"
    source: str = "config"


class PersonPresence(WorldModelBase):
    person_id: str
    name: str | None = None
    identity_confidence: float = 0.0
    position_hint: str | None = None
    last_seen_at: datetime
    last_heard_at: datetime | None = None
    source: str = "vision"


class DetectedObject(WorldModelBase):
    label: str
    confidence: float
    position_hint: str | None = None


class AmbientState(WorldModelBase):
    lighting: str | None = None
    noise_level: str | None = None
    activity_hint: str | None = None


class SceneState(WorldModelBase):
    description: str | None = None
    objects: list[DetectedObject] = Field(default_factory=list)
    ambient: AmbientState = Field(default_factory=AmbientState)
    observed_at: datetime
    stale: bool = False


class TimeContext(WorldModelBase):
    period: str
    hour: int
    is_quiet_hours: bool
    since_last_interaction_sec: float | None = None
    since_last_movement_sec: float | None = None


class WorldState(WorldModelBase):
    robot_position: Position | None = None
    places: dict[str, Place] = Field(default_factory=dict)
    people_present: dict[str, PersonPresence] = Field(default_factory=dict)
    scene: SceneState | None = None
    last_interaction_at: datetime | None = None
    last_movement_at: datetime | None = None


class WorldModel:
    def __init__(
        self,
        *,
        static_places: dict[str, PlaceConfig] | None = None,
        scene_ttl_sec: float = 300.0,
    ) -> None:
        self._scene_ttl_sec = scene_ttl_sec
        self._state = WorldState(
            places={
                name: Place(
                    name=name,
                    center=(place.x, place.y),
                    angle=place.angle,
                )
                for name, place in (static_places or {}).items()
            }
        )

    async def start(self, bus: EventBus) -> None:
        bus.subscribe("motion.position_updated", self._handle_event)
        bus.subscribe("vision.person_detected", self._handle_event)
        bus.subscribe("vision.scene_observed", self._handle_event)

    async def stop(self) -> None:
        return None

    async def _handle_event(self, event: Event) -> None:
        if event.event_type == "motion.position_updated":
            self._update_position(event)
        elif event.event_type == "vision.person_detected":
            self._upsert_person(event)
        elif event.event_type == "vision.scene_observed":
            self._replace_scene(event)

    def snapshot(self) -> WorldState:
        return self._state.model_copy(deep=True)

    def get_position(self) -> Position | None:
        if self._state.robot_position is None:
            return None
        return self._state.robot_position.model_copy(deep=True)

    def get_room(self) -> str | None:
        return self._state.robot_position.room if self._state.robot_position else None

    def resolve_place(self, name: str) -> Place | None:
        place = self._state.places.get(name)
        return place.model_copy(deep=True) if place else None

    def get_people_present(self, max_age_sec: float = 300.0) -> list[PersonPresence]:
        now = datetime.now(UTC)
        return [
            person.model_copy(deep=True)
            for person in self._state.people_present.values()
            if (now - person.last_seen_at).total_seconds() <= max_age_sec
        ]

    def get_scene(self) -> SceneState | None:
        scene = self._state.scene
        if scene is None:
            return None
        copied = scene.model_copy(deep=True)
        copied.stale = (datetime.now(UTC) - scene.observed_at).total_seconds() > self._scene_ttl_sec
        return copied

    def get_time_context(self) -> TimeContext:
        now = datetime.now(UTC)
        return TimeContext(
            period=_period_for_hour(now.hour),
            hour=now.hour,
            is_quiet_hours=0 <= now.hour < 7,
            since_last_interaction_sec=_seconds_since(now, self._state.last_interaction_at),
            since_last_movement_sec=_seconds_since(now, self._state.last_movement_at),
        )

    def is_person_nearby(self, name: str, max_age_sec: float = 60.0) -> bool:
        return any(person.name == name for person in self.get_people_present(max_age_sec))

    def _update_position(self, event: Event) -> None:
        x = _float_payload(event, "x")
        y = _float_payload(event, "y")
        if x is None or y is None:
            return
        self._state.robot_position = Position(
            x=x,
            y=y,
            angle=_float_payload(event, "angle"),
            room=self._derive_room(x, y),
            updated_at=event.occurred_at,
        )
        self._state.last_movement_at = event.occurred_at

    def _derive_room(self, x: float, y: float) -> str | None:
        for place in self._state.places.values():
            if hypot(x - place.center[0], y - place.center[1]) <= place.radius:
                return place.name
        return None

    def _upsert_person(self, event: Event) -> None:
        person_id = _str_payload(event, "person_id") or f"unknown-{uuid4().hex[:8]}"
        existing = self._state.people_present.get(person_id)
        name = _str_payload(event, "name")
        self._state.people_present[person_id] = PersonPresence(
            person_id=person_id,
            name=name if name is not None else (existing.name if existing is not None else None),
            identity_confidence=_float_payload(event, "confidence") or 0.0,
            position_hint=_str_payload(event, "position_hint"),
            last_seen_at=event.occurred_at,
            source=_str_payload(event, "source") or "vision",
        )

    def _replace_scene(self, event: Event) -> None:
        objects = event.payload.get("objects", [])
        detected: list[DetectedObject] = []
        if isinstance(objects, list):
            for item in objects:
                if not isinstance(item, dict):
                    continue
                detected.append(
                    DetectedObject(
                        label=str(item.get("label", "")),
                        confidence=_float_from_value(item.get("confidence")) or 0.0,
                        position_hint=(
                            str(item["position_hint"])
                            if item.get("position_hint") is not None
                            else None
                        ),
                    )
                )
        self._state.scene = SceneState(
            description=_str_payload(event, "description"),
            objects=detected,
            observed_at=event.occurred_at,
        )


def _period_for_hour(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 22:
        return "evening"
    return "night"


def _seconds_since(now: datetime, then: datetime | None) -> float | None:
    if then is None:
        return None
    return (now - then).total_seconds()


def _str_payload(event: Event, key: str) -> str | None:
    value = event.payload.get(key)
    return value if isinstance(value, str) else None


def _float_payload(event: Event, key: str) -> float | None:
    value = event.payload.get(key)
    return _float_from_value(value)


def _float_from_value(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None
