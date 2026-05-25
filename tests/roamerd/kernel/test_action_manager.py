import asyncio

import pytest

from roamerd.contracts.errors import ErrorCode
from roamerd.events import Event, Priority
from roamerd.kernel.action_manager import (
    ActionManager,
    ActionRequestError,
    ActionStatus,
    PreemptionScope,
)
from roamerd.kernel.event_bus import EventBus


@pytest.mark.asyncio
async def test_request_action_starts_action_and_publishes_event() -> None:
    bus = EventBus()
    manager = ActionManager(session_id="session-real")
    events: list[Event] = []

    async def handler(event: Event) -> None:
        events.append(event)

    bus.subscribe("action.started", handler)
    await manager.start(bus)

    action = await manager.request_action(
        "speech.speak",
        {"text": "hello"},
        resource="speaker",
        priority=Priority.HIGH,
        source_module="speech",
    )
    await bus.run_until_idle()

    assert not isinstance(action, ActionRequestError)
    assert action.status is ActionStatus.RUNNING
    assert action.payload == {"text": "hello"}
    assert events[0].payload["action_id"] == action.action_id
    assert events[0].payload["action_type"] == "speech.speak"
    assert events[0].session_id == "session-real"


@pytest.mark.asyncio
async def test_resource_busy_returns_error_without_admission_decision() -> None:
    bus = EventBus()
    manager = ActionManager()
    await manager.start(bus)

    first = await manager.request_action("speech.speak", {}, resource="speaker")
    second = await manager.request_action("speech.speak", {}, resource="speaker")

    assert not isinstance(first, ActionRequestError)
    assert isinstance(second, ActionRequestError)
    assert second.error_code is ErrorCode.BUSY


@pytest.mark.asyncio
async def test_resource_none_actions_can_run_concurrently() -> None:
    bus = EventBus()
    manager = ActionManager()
    await manager.start(bus)

    first = await manager.request_action("status.get", {}, resource="none")
    second = await manager.request_action("time.now", {}, resource="none")

    assert not isinstance(first, ActionRequestError)
    assert not isinstance(second, ActionRequestError)
    assert {action.action_id for action in manager.get_running_actions()} == {
        first.action_id,
        second.action_id,
    }


@pytest.mark.asyncio
async def test_complete_action_releases_resource_and_publishes_completed() -> None:
    bus = EventBus()
    manager = ActionManager()
    completed: list[Event] = []

    async def handler(event: Event) -> None:
        completed.append(event)

    bus.subscribe("action.completed", handler)
    await manager.start(bus)
    action = await manager.request_action("speech.speak", {}, resource="speaker")
    assert not isinstance(action, ActionRequestError)

    await manager.complete_action(action.action_id, {"ok": True})
    await bus.run_until_idle()
    next_action = await manager.request_action("speech.speak", {}, resource="speaker")

    assert manager.get_action(action.action_id).status is ActionStatus.COMPLETED
    assert not isinstance(next_action, ActionRequestError)
    assert completed[0].payload["action_id"] == action.action_id


@pytest.mark.asyncio
async def test_cancel_is_two_step_until_module_marks_cancelled() -> None:
    bus = EventBus()
    manager = ActionManager()
    cancel_requests: list[Event] = []

    async def handler(event: Event) -> None:
        cancel_requests.append(event)

    bus.subscribe("action.cancel_requested", handler)
    await manager.start(bus)
    action = await manager.request_action("speech.speak", {}, resource="speaker")
    assert not isinstance(action, ActionRequestError)

    await manager.cancel_action(action.action_id, "user_request")
    await bus.run_until_idle()

    assert manager.get_action(action.action_id).status is ActionStatus.RUNNING
    assert cancel_requests[0].payload["action_id"] == action.action_id

    await manager.mark_cancelled(action.action_id, "user_request")
    assert manager.get_action(action.action_id).status is ActionStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_times_out_to_cancelled_terminal_state() -> None:
    bus = EventBus()
    manager = ActionManager(preemption_timeout_sec=0.01)
    cancelled_events: list[Event] = []

    async def handler(event: Event) -> None:
        cancelled_events.append(event)

    bus.subscribe("action.cancelled", handler)
    await manager.start(bus)
    action = await manager.request_action("speech.speak", {}, resource="speaker")
    assert not isinstance(action, ActionRequestError)

    await manager.cancel_action(action.action_id, "user_request")
    await asyncio.sleep(0.03)
    await bus.run_until_idle()

    assert manager.get_action(action.action_id).status is ActionStatus.CANCELLED
    assert manager.get_running_actions("speaker") == []
    assert cancelled_events[0].payload == {
        "action_id": action.action_id,
        "reason": "cancel_timeout",
    }


@pytest.mark.asyncio
async def test_preempt_marks_running_action_preempting_and_module_ack_releases() -> None:
    bus = EventBus()
    manager = ActionManager()
    preempt_requests: list[Event] = []

    async def handler(event: Event) -> None:
        preempt_requests.append(event)

    bus.subscribe("action.preempt_requested", handler)
    await manager.start(bus)
    action = await manager.request_action("motion.goto", {}, resource="motion")
    assert not isinstance(action, ActionRequestError)

    preempted = await manager.preempt(
        PreemptionScope(
            target_resources=["motion"],
            reason="emergency",
            source_event="event-1",
        )
    )
    await bus.run_until_idle()

    assert preempted == [action.action_id]
    assert manager.get_action(action.action_id).status is ActionStatus.PREEMPTING
    assert preempt_requests[0].payload["action_id"] == action.action_id

    await manager.mark_preempted(action.action_id, "emergency")
    assert manager.get_action(action.action_id).status is ActionStatus.PREEMPTED
    assert await manager.request_action("motion.goto", {}, resource="motion")


@pytest.mark.asyncio
async def test_direct_preempt_times_out_to_preempted_terminal_state() -> None:
    bus = EventBus()
    manager = ActionManager(preemption_timeout_sec=0.01)
    preempted_events: list[Event] = []

    async def handler(event: Event) -> None:
        preempted_events.append(event)

    bus.subscribe("action.preempted", handler)
    await manager.start(bus)
    action = await manager.request_action("motion.goto", {}, resource="motion")
    assert not isinstance(action, ActionRequestError)

    await manager.preempt(
        PreemptionScope(
            target_resources=["motion"],
            reason="emergency",
            source_event="event-1",
        )
    )
    await asyncio.sleep(0.03)
    await bus.run_until_idle()

    assert manager.get_action(action.action_id).status is ActionStatus.PREEMPTED
    assert manager.get_running_actions("motion") == []
    assert preempted_events[0].payload == {
        "action_id": action.action_id,
        "reason": "preempt_timeout",
    }


@pytest.mark.asyncio
async def test_preempt_current_returns_waiting_action_and_hands_off_after_ack() -> None:
    bus = EventBus()
    manager = ActionManager(preemption_timeout_sec=1.0)
    started_events: list[Event] = []
    preempt_requests: list[Event] = []

    async def started_handler(event: Event) -> None:
        started_events.append(event)

    async def preempt_handler(event: Event) -> None:
        preempt_requests.append(event)

    bus.subscribe("action.started", started_handler)
    bus.subscribe("action.preempt_requested", preempt_handler)
    await manager.start(bus)
    old_action = await manager.request_action(
        "speech.speak",
        {},
        resource="speaker",
        priority=Priority.NORMAL,
    )
    assert not isinstance(old_action, ActionRequestError)

    new_action = await manager.request_action(
        "speech.speak",
        {"text": "urgent"},
        resource="speaker",
        priority=Priority.HIGH,
        preempt_current=True,
    )
    await bus.run_until_idle()

    assert not isinstance(new_action, ActionRequestError)
    assert manager.get_action(old_action.action_id).status is ActionStatus.PREEMPTING
    assert new_action.status is ActionStatus.WAITING_RESOURCE
    assert new_action.waiting_for_action_id == old_action.action_id
    assert preempt_requests[0].payload["action_id"] == old_action.action_id
    assert [event.payload["action_id"] for event in started_events] == [old_action.action_id]

    await manager.mark_preempted(old_action.action_id, "urgent_speech")
    await bus.run_until_idle()

    assert manager.get_action(old_action.action_id).status is ActionStatus.PREEMPTED
    assert manager.get_action(new_action.action_id).status is ActionStatus.RUNNING
    assert manager.get_running_actions("speaker")[0].action_id == new_action.action_id
    assert [event.payload["action_id"] for event in started_events] == [
        old_action.action_id,
        new_action.action_id,
    ]


@pytest.mark.asyncio
async def test_waiting_preempted_action_fails_if_handoff_times_out() -> None:
    bus = EventBus()
    manager = ActionManager(preemption_timeout_sec=0.01)
    failed_events: list[Event] = []

    async def failed_handler(event: Event) -> None:
        failed_events.append(event)

    bus.subscribe("action.failed", failed_handler)
    await manager.start(bus)
    old_action = await manager.request_action("motion.goto", {}, resource="motion")
    assert not isinstance(old_action, ActionRequestError)

    new_action = await manager.request_action(
        "motion.home",
        {},
        resource="motion",
        preempt_current=True,
    )
    assert not isinstance(new_action, ActionRequestError)

    await asyncio.sleep(0.03)
    await bus.run_until_idle()

    assert manager.get_action(old_action.action_id).status is ActionStatus.PREEMPTING
    assert manager.get_action(new_action.action_id).status is ActionStatus.FAILED
    assert manager.get_action(new_action.action_id).error == {
        "reason": "resource_preemption_timeout",
        "waiting_for_action_id": old_action.action_id,
    }
    assert failed_events[0].payload["action_id"] == new_action.action_id


@pytest.mark.asyncio
async def test_mark_detached_keeps_resource_occupied_and_queryable() -> None:
    bus = EventBus()
    manager = ActionManager()
    await manager.start(bus)
    action = await manager.request_action("motion.goto", {}, resource="motion")
    assert not isinstance(action, ActionRequestError)

    await manager.mark_detached(action.action_id)
    blocked = await manager.request_action("motion.goto", {}, resource="motion")

    assert manager.get_action(action.action_id).status is ActionStatus.RUNNING_DETACHED
    assert manager.get_running_actions("motion")[0].action_id == action.action_id
    assert isinstance(blocked, ActionRequestError)


@pytest.mark.asyncio
async def test_mark_detached_full_lifecycle_preempt_releases_resource() -> None:
    bus = EventBus()
    manager = ActionManager()
    await manager.start(bus)
    action = await manager.request_action("motion.goto", {}, resource="motion")
    assert not isinstance(action, ActionRequestError)

    await manager.mark_detached(action.action_id)
    blocked = await manager.request_action("motion.goto", {}, resource="motion")
    preempted = await manager.preempt(
        PreemptionScope(target_resources=["motion"], reason="test", source_event="test")
    )
    await manager.mark_preempted(action.action_id, "test")
    next_action = await manager.request_action("motion.goto", {}, resource="motion")

    assert isinstance(blocked, ActionRequestError)
    assert preempted == [action.action_id]
    assert manager.get_action(action.action_id).status is ActionStatus.PREEMPTED
    assert not isinstance(next_action, ActionRequestError)
    assert manager.get_running_actions("motion")[0].action_id == next_action.action_id


@pytest.mark.asyncio
async def test_module_unavailable_fails_running_actions_for_source_module() -> None:
    bus = EventBus()
    manager = ActionManager()
    failed_events: list[Event] = []

    async def handler(event: Event) -> None:
        failed_events.append(event)

    bus.subscribe("action.failed", handler)
    await manager.start(bus)
    action = await manager.request_action(
        "speech.speak",
        {},
        resource="speaker",
        source_module="speech",
    )
    assert not isinstance(action, ActionRequestError)

    await bus.publish(
        Event(
            event_type="system.health_changed",
            source="test",
            session_id="session-1",
            payload={"component": "speech", "status": "unavailable"},
        )
    )
    await bus.run_until_idle()
    next_action = await manager.request_action("speech.speak", {}, resource="speaker")

    assert manager.get_action(action.action_id).status is ActionStatus.FAILED
    assert manager.get_action(action.action_id).error == {"reason": "module_crashed"}
    assert failed_events[0].payload["action_id"] == action.action_id
    assert not isinstance(next_action, ActionRequestError)


@pytest.mark.asyncio
async def test_terminal_actions_are_pruned_to_bounded_recent_history() -> None:
    bus = EventBus()
    manager = ActionManager(
        terminal_retention_sec=0.01,
        recent_terminal_maxlen=3,
        orphan_timeout_sec=0,
    )
    await manager.start(bus)
    action_ids: list[str] = []

    for index in range(5):
        action = await manager.request_action("time.now", {"index": index}, resource="none")
        assert not isinstance(action, ActionRequestError)
        action_ids.append(action.action_id)
        await manager.complete_action(action.action_id, {"index": index})

    await asyncio.sleep(0.03)
    await manager.prune_terminal_actions()

    assert len(manager._actions) == 0
    assert manager.get_action(action_ids[0]) is None
    assert manager.get_action(action_ids[1]) is None
    assert [manager.get_action(action_id).action_id for action_id in action_ids[-3:]] == action_ids[
        -3:
    ]
    await manager.stop()


@pytest.mark.asyncio
async def test_terminal_cleanup_drops_stale_resource_lock() -> None:
    bus = EventBus()
    manager = ActionManager(terminal_retention_sec=0.01, orphan_timeout_sec=0)
    await manager.start(bus)
    action = await manager.request_action("motion.goto", {}, resource="motion")
    assert not isinstance(action, ActionRequestError)
    await manager.complete_action(action.action_id, {"ok": True})
    manager._resource_locks["motion"] = action.action_id

    await asyncio.sleep(0.03)
    await manager.prune_terminal_actions()

    assert manager._resource_locks == {}
    assert manager.get_action(action.action_id).status is ActionStatus.COMPLETED
    await manager.stop()


@pytest.mark.asyncio
async def test_orphan_running_action_fails_after_timeout_without_module_activity() -> None:
    bus = EventBus()
    manager = ActionManager(
        orphan_timeout_sec=0.01,
        orphan_scan_interval_sec=0.005,
        terminal_retention_sec=60,
    )
    failed_events: list[Event] = []

    async def handler(event: Event) -> None:
        failed_events.append(event)

    bus.subscribe("action.failed", handler)
    await manager.start(bus)
    action = await manager.request_action("speech.speak", {}, resource="speaker")
    assert not isinstance(action, ActionRequestError)

    await asyncio.sleep(0.04)
    await bus.run_until_idle()

    assert manager.get_action(action.action_id).status is ActionStatus.FAILED
    assert manager.get_action(action.action_id).error == {"reason": "orphan_timeout"}
    assert manager.get_running_actions("speaker") == []
    assert failed_events[0].payload == {
        "action_id": action.action_id,
        "error": {"reason": "orphan_timeout"},
    }
    await manager.stop()


@pytest.mark.asyncio
async def test_orphan_detection_keeps_action_with_module_activity_running() -> None:
    bus = EventBus()
    manager = ActionManager(
        orphan_timeout_sec=0.01,
        orphan_scan_interval_sec=0.005,
        terminal_retention_sec=60,
    )
    await manager.start(bus)
    action = await manager.request_action("motion.goto", {}, resource="motion")
    assert not isinstance(action, ActionRequestError)
    await bus.publish(
        Event(
            event_type="motion.started",
            source="motion",
            session_id="session-1",
            action_id=action.action_id,
            payload={"action_id": action.action_id},
        )
    )
    await bus.run_until_idle()

    await asyncio.sleep(0.04)
    await bus.run_until_idle()

    assert manager.get_action(action.action_id).status is ActionStatus.RUNNING
    assert manager.get_running_actions("motion")[0].action_id == action.action_id
    await manager.stop()
