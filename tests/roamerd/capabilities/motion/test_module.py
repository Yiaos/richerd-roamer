import pytest

from roamerd.capabilities.motion.drivers.mock_ros2 import MockRos2NavDriver
from roamerd.capabilities.motion.drivers.ros2_nav_base import MotionDriver
from roamerd.capabilities.motion.module import MotionModule
from roamerd.events import Event
from roamerd.kernel import ActionManager, ActionRequestError, EventBus, PreemptionScope
from roamerd.kernel.action_manager import ActionStatus


def test_motion_protocol_accepts_mock_driver() -> None:
    driver: MotionDriver = MockRos2NavDriver()

    assert driver is not None


@pytest.mark.asyncio
async def test_motion_home_action_lifecycle() -> None:
    bus = EventBus()
    actions = ActionManager()
    driver = MockRos2NavDriver()
    module = MotionModule(driver=driver, action_manager=actions, session_id="session-1")
    events: list[Event] = []

    async def handler(event: Event) -> None:
        events.append(event)

    bus.subscribe_pattern("motion.*", handler)
    await actions.start(bus)
    await module.start(bus)
    action = await actions.request_action(
        "motion.home",
        {},
        resource="motion",
        source_module="motion",
    )
    assert not isinstance(action, ActionRequestError)

    await bus.run_until_idle()

    assert driver.homed is True
    assert [event.event_type for event in events] == ["motion.started", "motion.completed"]
    assert actions.get_action(action.action_id).status is ActionStatus.COMPLETED


@pytest.mark.asyncio
async def test_motion_preempt_request_stops_driver_and_marks_preempted() -> None:
    bus = EventBus()
    actions = ActionManager()
    driver = MockRos2NavDriver(complete_immediately=False)
    module = MotionModule(driver=driver, action_manager=actions, session_id="session-1")
    await actions.start(bus)
    await module.start(bus)
    action = await actions.request_action(
        "motion.goto",
        {"target": {"x": 1, "y": 2}},
        resource="motion",
        source_module="motion",
    )
    assert not isinstance(action, ActionRequestError)

    await bus.run_until_idle()
    await actions.preempt(
        PreemptionScope(target_resources=["motion"], reason="test", source_event="test")
    )
    await bus.run_until_idle()

    assert driver.stopped is True
    assert actions.get_action(action.action_id).status is ActionStatus.PREEMPTED
