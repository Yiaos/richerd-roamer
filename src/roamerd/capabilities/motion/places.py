from __future__ import annotations

from datetime import datetime
from math import hypot

from pydantic import BaseModel, ConfigDict


class Place(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    x: float
    y: float
    angle: float | None = None
    tolerance: float = 300.0
    map_id: str | None = None
    map_hash: str | None = None
    verification_status: str = "unverified_static"
    verified_at: datetime | None = None


class PlaceRegistry:
    def __init__(self, places: list[Place]) -> None:
        self._places = {place.name: place for place in places}

    def resolve(self, name: str) -> Place:
        return self._places[name].model_copy(deep=True)

    def list(self) -> list[Place]:
        return [place.model_copy(deep=True) for place in self._places.values()]

    def nearest(self, x: float, y: float) -> Place:
        nearest = min(
            self._places.values(),
            key=lambda place: hypot(x - place.x, y - place.y),
        )
        return nearest.model_copy(deep=True)

    def invalidate_for_map(self, *, map_id: str | None, map_hash: str | None) -> None:
        for name, place in self._places.items():
            if place.map_id == map_id and place.map_hash == map_hash:
                continue
            self._places[name] = place.model_copy(update={"verification_status": "stale"})
