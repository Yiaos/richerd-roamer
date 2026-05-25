import json

import pytest

from roamerd.app import create_app
from roamerd.config.schema import IntentConfig, RoamerdConfig
from roamerd.events import Event, Priority
from roamerd.kernel.action_manager import ActionStatus


@pytest.mark.asyncio
async def test_voice_spine_proof_transcript_to_mock_speech_completion() -> None:
    app = create_app(
        RoamerdConfig.model_validate(
            {
                "policy": {
                    "local_intents": [
                        IntentConfig(
                            name="say_hello",
                            action="speech.speak",
                            patterns=["打招呼"],
                            priority=Priority.NORMAL,
                        ).model_dump()
                    ]
                }
            }
        )
    )
    await app.start()
    observed: list[Event] = []

    async def observe(event: Event) -> None:
        observed.append(event)

    app.event_bus.subscribe_pattern("*", observe)

    await app.event_bus.publish(
        Event(
            event_type="hearing.transcript_ready",
            source="test",
            session_id=app.session_id,
            turn_id="turn-1",
            priority=Priority.HIGH,
            payload={"text": "请打招呼"},
        )
    )
    await app.event_bus.run_until_idle()

    completed = [
        event
        for event in observed
        if event.event_type == "action.completed"
        and event.source == "action_manager"
        and event.turn_id == "turn-1"
    ]
    assert len(completed) == 1
    action_id = str(completed[0].payload["action_id"])

    assert app.action_manager.get_action(action_id).status is ActionStatus.COMPLETED
    assert app.state_manager.snapshot().last_interaction_at is not None
    assert any(event.event_type == "speech.playback_completed" for event in observed)
    assert any(
        event["event_type"] == "action.completed" and event["session_id"] == app.session_id
        for event in read_trace_events(app)
    )

    await app.stop()


def read_trace_events(app) -> list[dict[str, object]]:
    app.observability.flush()
    return [
        json.loads(line)
        for path in sorted(app.observability.log_dir.glob("roamerd-*.jsonl*"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
