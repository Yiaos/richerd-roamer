import asyncio

import pytest

from roamerd.config.schema import PlaceConfig
from roamerd.events import Event, Priority
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.world_model import Place, WorldModel


def make_event(event_type: str, payload: dict[str, object] | None = None) -> Event:
    return Event(
        event_type=event_type,
        source="test",
        session_id="session-1",
        priority=Priority.NORMAL,
        payload=payload or {},
    )


@pytest.mark.asyncio
async def test_motion_position_updates_robot_position_and_room() -> None:
    bus = EventBus()
    model = WorldModel(static_places={"客厅": PlaceConfig(x=10, y=10, angle=0)})
    await model.start(bus)

    await bus.publish(make_event("motion.position_updated", {"x": 12.0, "y": 9.0, "angle": 1.0}))
    await bus.run_until_idle()

    position = model.get_position()
    assert position is not None
    assert position.x == 12.0
    assert position.room == "客厅"
    assert model.get_room() == "客厅"


def test_resolve_place_from_static_config() -> None:
    model = WorldModel(static_places={"阳台": PlaceConfig(x=2082, y=2377, angle=111)})

    place = model.resolve_place("阳台")

    assert place == Place(
        name="阳台",
        center=(2082.0, 2377.0),
        radius=250.0,
        angle=111.0,
        frame="valetudo_pixel",
    )
    assert model.resolve_place("不存在") is None


@pytest.mark.asyncio
async def test_person_detected_upserts_without_duplicates() -> None:
    bus = EventBus()
    model = WorldModel()
    await model.start(bus)

    await bus.publish(
        make_event(
            "vision.person_detected",
            {"person_id": "richerd", "name": "Richerd", "confidence": 0.8},
        )
    )
    await bus.run_until_idle()
    first_seen = model.get_people_present()[0].last_seen_at

    await asyncio.sleep(0.001)
    await bus.publish(
        make_event(
            "vision.person_detected",
            {"person_id": "richerd", "name": "Richerd", "confidence": 0.9},
        )
    )
    await bus.run_until_idle()

    people = model.get_people_present()
    assert len(people) == 1
    assert people[0].identity_confidence == 0.9
    assert people[0].last_seen_at > first_seen
    assert model.is_person_nearby("Richerd") is True


@pytest.mark.asyncio
async def test_unknown_person_gets_temp_id_and_ttl_filters_presence() -> None:
    bus = EventBus()
    model = WorldModel()
    await model.start(bus)

    await bus.publish(make_event("vision.person_detected", {"confidence": 0.3}))
    await bus.run_until_idle()

    people = model.get_people_present()
    assert len(people) == 1
    assert people[0].person_id.startswith("unknown-")
    assert people[0].name is None

    await asyncio.sleep(0.002)

    assert model.get_people_present(max_age_sec=0.001) == []


@pytest.mark.asyncio
async def test_scene_observed_replaces_scene_state() -> None:
    bus = EventBus()
    model = WorldModel(scene_ttl_sec=0.001)
    await model.start(bus)

    await bus.publish(
        make_event(
            "vision.scene_observed",
            {"description": "客厅灯亮着", "objects": [{"label": "灯", "confidence": 0.9}]},
        )
    )
    await bus.run_until_idle()

    scene = model.get_scene()
    assert scene is not None
    assert scene.description == "客厅灯亮着"
    assert scene.objects[0].label == "灯"

    await asyncio.sleep(0.002)

    stale_scene = model.get_scene()
    assert stale_scene is not None
    assert stale_scene.stale is True


@pytest.mark.asyncio
async def test_cognition_events_do_not_mutate_world_model() -> None:
    bus = EventBus()
    model = WorldModel()
    await model.start(bus)

    await bus.publish(make_event("cognition.response_received", {"kind": "speak"}))
    await bus.run_until_idle()

    assert model.snapshot().people_present == {}
    assert model.get_position() is None
    assert model.get_scene() is None


def test_restart_clears_people_but_restores_places_from_config() -> None:
    first = WorldModel(static_places={"客厅": PlaceConfig(x=1, y=2)})
    second = WorldModel(static_places={"客厅": PlaceConfig(x=1, y=2)})

    assert first.get_people_present() == []
    assert second.resolve_place("客厅") is not None


def test_time_context_is_computed_on_read() -> None:
    model = WorldModel()

    context = model.get_time_context()

    assert 0 <= context.hour <= 23
    assert context.period in {"morning", "afternoon", "evening", "night"}
