import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from roamerd.capabilities.body_status import BodyStatusModule, BodyStatusSnapshot
from roamerd.capabilities.reminder import ReminderModule
from roamerd.capabilities.speech.drivers.tts_base import SynthResult
from roamerd.capabilities.speech.module import SpeechModule
from roamerd.capabilities.vision.drivers.camera_base import CaptureResult
from roamerd.capabilities.vision.module import VisionModule
from roamerd.config.schema import PlaceConfig
from roamerd.events import Event
from roamerd.kernel import ActionManager, EventBus, PolicyEngine, StateManager, WorldModel


class FakeCamera:
    async def capture(
        self,
        output_path: Path,
        *,
        width: int | None = None,
        height: int | None = None,
    ) -> CaptureResult:
        return CaptureResult(
            path=output_path,
            timestamp=datetime.now(UTC),
            width=width,
            height=height,
        )


class FakeBody:
    async def snapshot(self) -> BodyStatusSnapshot:
        return BodyStatusSnapshot(
            hostname="roamer",
            uptime_sec=1,
            cpu_percent=2,
            memory_used_mb=3,
            memory_total_mb=4,
            temperature_c=None,
            disk_used_mb=5,
            disk_total_mb=6,
            network_interfaces=["wlan0"],
        )


class FakeTts:
    async def synthesize(self, text: str, output_path: Path) -> SynthResult:
        return SynthResult(path=output_path, duration_ms=1)


class FakePlayback:
    async def play(self, path: Path) -> None:
        return None


@pytest.mark.asyncio
async def test_b2_capture_body_status_and_reminder_flow(tmp_path: Path) -> None:
    bus = EventBus()
    actions = ActionManager()
    state = StateManager(session_id="session-1")
    world = WorldModel(static_places={"客厅": PlaceConfig(x=1, y=2)})
    policy = PolicyEngine(session_id="session-1")
    vision = VisionModule(
        camera=FakeCamera(),
        action_manager=actions,
        output_dir=tmp_path,
        session_id="session-1",
    )
    body = BodyStatusModule(
        provider=FakeBody(),
        action_manager=actions,
        session_id="session-1",
    )
    speech = SpeechModule(
        tts=FakeTts(),
        playback=FakePlayback(),
        action_manager=actions,
        output_dir=tmp_path,
        session_id="session-1",
    )
    reminder = ReminderModule(action_manager=actions, session_id="session-1")
    events: list[Event] = []

    async def handler(event: Event) -> None:
        events.append(event)

    bus.subscribe_pattern("*", handler)
    await actions.start(bus)
    await state.start(bus)
    await world.start(bus)
    await policy.start(bus, actions, state, world)
    await vision.start(bus)
    await body.start(bus)
    await speech.start(bus)
    await reminder.start(bus)
    for module in ("vision", "body", "speech"):
        await bus.publish(
            Event(
                event_type="system.module_ready",
                source="test",
                session_id="session-1",
                payload={"module": module},
            )
        )
    runner = asyncio.create_task(bus.run())

    await bus.publish(
        Event(
            event_type="hearing.transcript_ready",
            source="test",
            session_id="session-1",
            payload={"text": "拍张照"},
        )
    )
    while not any(event.event_type == "vision.image_captured" for event in events):
        await asyncio.sleep(0.01)

    await bus.publish(
        Event(
            event_type="hearing.transcript_ready",
            source="test",
            session_id="session-1",
            payload={"text": "状态"},
        )
    )
    while not any(
        event.event_type == "action.completed"
        and actions.get_action(str(event.payload["action_id"])).action_type == "sense"
        for event in events
    ):
        await asyncio.sleep(0.01)

    await bus.publish(
        Event(
            event_type="hearing.transcript_ready",
            source="test",
            session_id="session-1",
            payload={"text": "1秒后提醒我喝水"},
        )
    )
    while not any(
        event.event_type == "action.started"
        and actions.get_action(str(event.payload["action_id"])).payload == {"text": "提醒：喝水"}
        for event in events
    ):
        await asyncio.sleep(0.01)

    await reminder.stop()
    await speech.stop()
    await body.stop()
    await vision.stop()
    await bus.stop()
    await runner

    assert any(event.event_type == "vision.image_captured" for event in events)
    assert any(
        event.event_type == "action.completed"
        and actions.get_action(str(event.payload["action_id"])).action_type == "sense"
        and actions.get_action(str(event.payload["action_id"])).result["hostname"] == "roamer"
        for event in events
    )
