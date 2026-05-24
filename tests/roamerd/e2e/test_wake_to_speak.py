import asyncio

import pytest

from roamerd.app import create_app
from roamerd.config.schema import RoamerdConfig
from roamerd.events import Event


@pytest.mark.asyncio
async def test_transcript_routes_to_cognition_response_then_speech_playback() -> None:
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
            payload={"text": "讲个笑话"},
        )
    )
    while not any(event.event_type == "cognition.request_needed" for event in events):
        await asyncio.sleep(0.01)

    await app.event_bus.publish(
        Event(
            event_type="cognition.response_received",
            source="test",
            session_id=app.session_id,
            payload={
                "action_request": {
                    "action_type": "speech.speak",
                    "resource": "speaker",
                    "payload": {"text": "好的"},
                    "source": "mock_cognition",
                }
            },
        )
    )
    while not any(event.event_type == "speech.playback_completed" for event in events):
        await asyncio.sleep(0.01)

    await app.stop()
    await runner

    assert any(event.event_type == "cognition.request_needed" for event in events)
    assert any(event.event_type == "speech.playback_completed" for event in events)
