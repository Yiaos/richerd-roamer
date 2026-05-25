import asyncio

import pytest

from roamerd.events import Event, Priority
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.state_manager import HealthState, StateManager


def make_event(event_type: str, payload: dict[str, object] | None = None) -> Event:
    return Event(
        event_type=event_type,
        source="test",
        session_id="session-1",
        priority=Priority.NORMAL,
        payload=payload or {},
    )


@pytest.mark.asyncio
async def test_hearing_events_update_audio_state() -> None:
    bus = EventBus()
    state = StateManager(session_id="session-1")
    await state.start(bus)

    await bus.publish(make_event("hearing.recording_started"))
    await bus.run_until_idle()
    assert state.is_listening is True

    await bus.publish(make_event("hearing.transcript_ready"))
    await bus.run_until_idle()

    snapshot = state.snapshot()
    assert snapshot.audio.listening is False
    assert snapshot.audio.stt_active is False
    assert snapshot.last_interaction_at is not None


@pytest.mark.asyncio
async def test_motion_events_update_motion_state() -> None:
    bus = EventBus()
    state = StateManager(session_id="session-1")
    await state.start(bus)

    await bus.publish(make_event("motion.started"))
    await bus.publish(make_event("motion.position_updated", {"x": 10.0, "y": 20.0, "angle": 1.5}))
    await bus.publish(make_event("motion.status_updated", {"battery_percent": 75, "docked": False}))
    await bus.run_until_idle()

    snapshot = state.snapshot()
    assert snapshot.motion.moving is True
    assert snapshot.motion.position is not None
    assert snapshot.motion.position.x == 10.0
    assert snapshot.motion.battery_percent == 75
    assert snapshot.motion.docked is False

    await bus.publish(make_event("motion.completed"))
    await bus.run_until_idle()
    assert state.is_moving is False


@pytest.mark.asyncio
async def test_snapshot_mutation_does_not_mutate_internal_state() -> None:
    bus = EventBus()
    state = StateManager(session_id="session-1")
    await state.start(bus)
    await bus.publish(make_event("speech.playback_started"))
    await bus.run_until_idle()

    snapshot = state.snapshot()
    snapshot.audio.playback_active = False

    assert state.snapshot().audio.playback_active is True


@pytest.mark.asyncio
async def test_health_tracking_for_modules_and_bridges() -> None:
    bus = EventBus()
    state = StateManager(session_id="session-1")
    await state.start(bus)

    await bus.publish(make_event("system.module_ready", {"module": "hearing"}))
    await bus.publish(
        make_event("system.health_changed", {"component": "hearing", "status": "degraded"})
    )
    await bus.publish(
        make_event(
            "system.health_changed",
            {"component": "control", "status": "unavailable", "kind": "bridge"},
        )
    )
    await bus.run_until_idle()

    assert state.get_module_health("hearing") is HealthState.DEGRADED
    assert state.get_bridge_health("control") is HealthState.UNAVAILABLE
    assert state.get_module_health("missing") is HealthState.UNAVAILABLE


@pytest.mark.asyncio
async def test_playback_stale_after_timeout() -> None:
    bus = EventBus()
    state = StateManager(session_id="session-1", playback_stale_after_sec=0.01)
    await state.start(bus)

    await bus.publish(make_event("speech.playback_started"))
    await bus.run_until_idle()
    assert state.playback_stale is False

    await asyncio.sleep(0.02)

    assert state.playback_stale is True


@pytest.mark.asyncio
async def test_playback_generation_advances_on_start_and_finish() -> None:
    bus = EventBus()
    state = StateManager(session_id="session-1")
    await state.start(bus)

    assert state.snapshot().audio.playback_generation == 0

    await bus.publish(make_event("speech.playback_started"))
    await bus.run_until_idle()
    started_generation = state.snapshot().audio.playback_generation

    await bus.publish(make_event("speech.playback_completed"))
    await bus.run_until_idle()

    assert started_generation == 1
    assert state.snapshot().audio.playback_generation == 2


@pytest.mark.asyncio
async def test_cognition_unavailable_updates_query_flag() -> None:
    bus = EventBus()
    state = StateManager(session_id="session-1")
    await state.start(bus)

    await bus.publish(make_event("cognition.unavailable", {"reason": "timeout"}))
    await bus.run_until_idle()

    assert state.cognition_available is False
    assert state.snapshot().cognition_available is False

    await bus.publish(
        make_event(
            "system.health_changed",
            {"component": "cognition", "status": "healthy", "kind": "bridge"},
        )
    )
    await bus.run_until_idle()

    assert state.cognition_available is True
    assert state.snapshot().cognition_available is True


@pytest.mark.asyncio
async def test_unknown_event_does_not_crash() -> None:
    bus = EventBus()
    state = StateManager(session_id="session-1")
    await state.start(bus)

    await bus.publish(make_event("system.startup", {"session_id": "session-1"}))
    await bus.run_until_idle()

    assert state.snapshot().session_id == "session-1"


@pytest.mark.asyncio
async def test_mode_is_derived_from_current_state() -> None:
    bus = EventBus()
    state = StateManager(session_id="session-1")
    await state.start(bus)

    assert state.snapshot().mode == "idle"

    await bus.publish(make_event("speech.playback_started"))
    await bus.run_until_idle()
    assert state.snapshot().mode == "speaking"

    await bus.publish(make_event("speech.playback_completed"))
    await bus.publish(make_event("motion.started"))
    await bus.run_until_idle()
    assert state.snapshot().mode == "moving"
