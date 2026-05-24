import pytest

from roamerd.kernel import ActionManager, ActionRequestError, EventBus
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
