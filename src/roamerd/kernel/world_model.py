"""Grounded physical world state."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field

from roamerd.config.schema import PlaceConfig, WorldModelConfig
from roamerd.events.base import Event
from roamerd.events.motion import Position
from roamerd.kernel.event_bus import EventBus


class Place(BaseModel):
    name: str
    pose: Position
    radius: float = 150.0
    source: str = "config"


class PersonPresence(BaseModel):
    person_id: str
    name: str | None = None
    identity_confidence: float = 0.0
    position_hint: str | None = None
    last_seen_at: datetime
    last_heard_at: datetime | None = None
    source: str = "vision"


class SceneState(BaseModel):
    description: str | None = None
    objects: list[str] = Field(default_factory=list)
    image_path: str | None = None
    model: str = "local"
    observed_at: datetime
    stale: bool = False


class TimeContext(BaseModel):
    period: str
    hour: int
    is_quiet_hours: bool
    since_last_interaction_sec: float | None = None
    since_last_movement_sec: float | None = None


class WorldState(BaseModel):
    robot_position: Position | None = None
    places: dict[str, Place] = Field(default_factory=dict)
    people_present: list[PersonPresence] = Field(default_factory=list)
    scene: SceneState | None = None
    last_image_path: str | None = None


class WorldModel:
    def __init__(self, config: WorldModelConfig) -> None:
        self._scene_ttl_sec = config.scene_ttl_sec
        self._state = WorldState(
            places={name: _place_from_config(name, place) for name, place in config.places.items()}
        )
        self._last_interaction_at: datetime | None = None
        self._last_movement_at: datetime | None = None

    async def start(self, bus: EventBus) -> None:
        for event_type in (
            "motion.position_updated",
            "vision.person_detected",
            "vision.scene_observed",
            "vision.image_captured",
            "hearing.transcript_ready",
        ):
            bus.subscribe(event_type, self._handle_event)

    async def stop(self) -> None:
        return None

    def snapshot(self) -> WorldState:
        state = self._state.model_copy(deep=True)
        if state.scene is not None:
            state.scene.stale = self._scene_is_stale(state.scene)
        return state

    def get_position(self) -> Position | None:
        return (
            self._state.robot_position.model_copy(deep=True) if self._state.robot_position else None
        )

    def get_room(self) -> str | None:
        position = self._state.robot_position
        if position is None:
            return None
        for place in self._state.places.values():
            if (
                place.pose.frame == position.frame
                and _distance(position, place.pose) <= place.radius
            ):
                return place.name
        return None

    def resolve_place(self, name: str) -> Place | None:
        place = self._state.places.get(name)
        return place.model_copy(deep=True) if place is not None else None

    def get_people_present(self, max_age_sec: float = 300.0) -> list[PersonPresence]:
        now = datetime.now(timezone.utc)
        return [
            person.model_copy(deep=True)
            for person in self._state.people_present
            if (now - person.last_seen_at).total_seconds() < max_age_sec
        ]

    def get_scene(self) -> SceneState | None:
        if self._state.scene is None:
            return None
        scene = self._state.scene.model_copy(deep=True)
        scene.stale = self._scene_is_stale(scene)
        return scene

    def get_time_context(self) -> TimeContext:
        now = datetime.now(timezone.utc)
        return TimeContext(
            period=_period(now.hour),
            hour=now.hour,
            is_quiet_hours=0 <= now.hour < 7,
            since_last_interaction_sec=_seconds_since(self._last_interaction_at, now),
            since_last_movement_sec=_seconds_since(self._last_movement_at, now),
        )

    def is_person_nearby(self, name: str, max_age_sec: float = 60.0) -> bool:
        return any(person.name == name for person in self.get_people_present(max_age_sec))

    async def _handle_event(self, event: Event) -> None:
        if event.event_type == "motion.position_updated":
            raw = event.payload.get("position")
            if isinstance(raw, dict):
                self._state.robot_position = Position.model_validate(raw)
                self._last_movement_at = event.occurred_at
        elif event.event_type == "vision.person_detected":
            person_id = str(
                event.payload.get("embedding_id") or event.payload.get("name") or uuid4().hex[:12]
            )
            existing = next(
                (item for item in self._state.people_present if item.person_id == person_id), None
            )
            if existing is None:
                self._state.people_present.append(
                    PersonPresence(
                        person_id=person_id,
                        name=str(event.payload.get("name")) if event.payload.get("name") else None,
                        identity_confidence=float(event.payload.get("confidence", 0.0)),
                        last_seen_at=event.occurred_at,
                    )
                )
            else:
                if event.payload.get("name"):
                    existing.name = str(event.payload["name"])
                existing.last_seen_at = event.occurred_at
                existing.identity_confidence = float(
                    event.payload.get("confidence", existing.identity_confidence)
                )
        elif event.event_type == "vision.scene_observed":
            objects = event.payload.get("objects")
            self._state.scene = SceneState(
                description=str(event.payload.get("description"))
                if event.payload.get("description")
                else None,
                objects=[str(item) for item in objects] if isinstance(objects, list) else [],
                image_path=str(event.payload.get("image_path"))
                if event.payload.get("image_path")
                else None,
                model=str(event.payload.get("model", "local")),
                observed_at=event.occurred_at,
            )
        elif event.event_type == "vision.image_captured":
            self._state.last_image_path = str(event.payload.get("path", ""))
        elif event.event_type == "hearing.transcript_ready":
            self._last_interaction_at = event.occurred_at

    def _scene_is_stale(self, scene: SceneState) -> bool:
        return (
            datetime.now(timezone.utc) - scene.observed_at
        ).total_seconds() > self._scene_ttl_sec


def _place_from_config(name: str, config: PlaceConfig) -> Place:
    return Place(
        name=name, pose=Position.model_validate(config.pose.model_dump()), radius=config.radius
    )


def _distance(left: Position, right: Position) -> float:
    return math.hypot(left.x - right.x, left.y - right.y)


def _seconds_since(value: datetime | None, now: datetime) -> float | None:
    return None if value is None else (now - value).total_seconds()


def _period(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 22:
        return "evening"
    return "night"
