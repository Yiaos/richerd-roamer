import asyncio

import pytest

from roamerd.app import create_app
from roamerd.config.schema import RoamerdConfig
from roamerd.events import Event


@pytest.mark.asyncio
async def test_local_motion_intent_goes_home_without_cognition() -> None:
    app = create_app(RoamerdConfig())
    events: list[Event] = []

    async def handler(event: Event) -> None:
        events.append(event)

    app.event_bus.subscribe_pattern("*", handler)
    await app.start()
    runner = asyncio.create_task(app.event_bus.run())

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

    await app.stop()
    await runner

    assert not any(event.event_type == "cognition.request_needed" for event in events)
    assert any(event.event_type == "motion.completed" for event in events)


@pytest.mark.asyncio
async def test_catalog_composition_no_match_routes_to_cognition() -> None:
    app = create_app(RoamerdConfig())
    policy = app.policy_engine

    assert policy.match_local_intent("停").action_type == "emergency_stop"
    assert policy.match_local_intent("回充电").action_type == "motion.home"
    assert policy.match_local_intent("1秒后提醒我喝水").action_type == "remind.schedule"
    assert policy.match_local_intent("拍张照").action_type == "watch"
    assert policy.match_local_intent("讲个笑话").matched is False
