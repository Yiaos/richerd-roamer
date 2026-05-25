import asyncio

import pytest

from roamerd.kernel import ActionManager, ActionRequestError, EventBus, PreemptionScope
from roamerd.kernel.action_manager import ActionStatus


@pytest.mark.asyncio
async def test_running_detached_action_is_queryable_and_preemptable() -> None:
    bus = EventBus()
    actions = ActionManager()
    await actions.start(bus)
    action = await actions.request_action("motion.goto", {}, resource="motion")
    assert not isinstance(action, ActionRequestError)

    await actions.mark_detached(action.action_id)

    assert actions.get_action(action.action_id).status is ActionStatus.RUNNING_DETACHED
    assert actions.get_running_actions("motion")[0].action_id == action.action_id

    preempted = await actions.preempt(
        PreemptionScope(target_resources=["motion"], reason="emergency", source_event="test")
    )

    assert preempted == [action.action_id]
    assert actions.get_action(action.action_id).status is ActionStatus.PREEMPTING


@pytest.mark.asyncio
async def test_running_detached_action_can_complete_and_release_resource() -> None:
    bus = EventBus()
    actions = ActionManager()
    await actions.start(bus)
    action = await actions.request_action("motion.goto", {}, resource="motion")
    assert not isinstance(action, ActionRequestError)

    await actions.mark_detached(action.action_id)
    await actions.complete_action(action.action_id, {"ok": True})
    next_action = await actions.request_action("motion.goto", {}, resource="motion")

    assert actions.get_action(action.action_id).status is ActionStatus.COMPLETED
    assert not isinstance(next_action, ActionRequestError)


@pytest.mark.asyncio
async def test_running_detached_action_cancel_timeout_releases_resource() -> None:
    bus = EventBus()
    actions = ActionManager(preemption_timeout_sec=0.01)
    await actions.start(bus)
    action = await actions.request_action("motion.goto", {}, resource="motion")
    assert not isinstance(action, ActionRequestError)

    await actions.mark_detached(action.action_id)
    await actions.cancel_action(action.action_id, "client_cancelled")
    await asyncio.sleep(0.03)

    next_action = await actions.request_action("motion.goto", {}, resource="motion")

    assert actions.get_action(action.action_id).status is ActionStatus.CANCELLED
    assert not isinstance(next_action, ActionRequestError)
