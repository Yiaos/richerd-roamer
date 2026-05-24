import asyncio

import pytest

from roamerd.app import create_app
from roamerd.config.schema import RoamerdConfig
from roamerd.events import Event


@pytest.mark.asyncio
async def test_cognition_unavailable_still_allows_local_intent_and_rejects_complex_text() -> None:
    app = create_app(RoamerdConfig())
    events: list[Event] = []

    async def handler(event: Event) -> None:
        events.append(event)

    app.event_bus.subscribe_pattern("*", handler)
    await app.start()
    runner = asyncio.create_task(app.event_bus.run())

    await app.event_bus.publish(
        Event(
            event_type="cognition.unavailable",
            source="test",
            session_id=app.session_id,
            payload={"reason": "offline"},
        )
    )
    await app.event_bus.publish(
        Event(
            event_type="hearing.transcript_ready",
            source="test",
            session_id=app.session_id,
            payload={"text": "回充电"},
        )
    )
    while not any(event.event_type == "motion.completed" for event in events):
        await asyncio.sleep(0.01)

    await app.event_bus.publish(
        Event(
            event_type="hearing.transcript_ready",
            source="test",
            session_id=app.session_id,
            payload={"text": "讲个笑话"},
        )
    )
    while not any(event.event_type == "speech.playback_completed" for event in events):
        await asyncio.sleep(0.01)

    await app.stop()
    await runner

    assert any(event.event_type == "motion.completed" for event in events)
    assert any(event.event_type == "speech.playback_completed" for event in events)


@pytest.mark.asyncio
async def test_matched_motion_intent_with_unavailable_module_rejects_without_cognition() -> None:
    app = create_app(RoamerdConfig())
    events: list[Event] = []

    async def handler(event: Event) -> None:
        events.append(event)

    app.event_bus.subscribe_pattern("*", handler)
    await app.start()
    runner = asyncio.create_task(app.event_bus.run())
    await app.event_bus.publish(
        Event(
            event_type="system.health_changed",
            source="test",
            session_id=app.session_id,
            payload={"component": "motion", "status": "unavailable"},
        )
    )
    await app.event_bus.publish(
        Event(
            event_type="hearing.transcript_ready",
            source="test",
            session_id=app.session_id,
            payload={"text": "回充电"},
        )
    )
    while not any(event.event_type == "policy.admission_rejected" for event in events):
        await asyncio.sleep(0.01)

    await app.stop()
    await runner

    assert not any(event.event_type == "cognition.request_needed" for event in events)
    assert any(
        event.event_type == "policy.admission_rejected"
        and event.payload["reason"] == "motion module unavailable"
        for event in events
    )
