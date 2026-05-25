import pytest

from roamerd.events import Event
from roamerd.kernel import ActionManager, ActionRequestError, EventBus
from roamerd.kernel.action_manager import ActionStatus
from roamerd.runtime.supervisor import Supervisor


class CrashingModule:
    name = "speech"
    events_produced: list[str] = []
    events_consumed: list[str] = []
    resources = ["speaker"]

    async def start(self, bus: EventBus) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def health_check(self) -> str:
        raise RuntimeError("module crashed")


@pytest.mark.asyncio
async def test_module_crash_health_event_fails_owned_running_action() -> None:
    bus = EventBus()
    actions = ActionManager()
    supervisor = Supervisor(bus, health_interval_sec=999)
    supervisor.register_module(CrashingModule())
    health_events: list[Event] = []

    async def health_handler(event: Event) -> None:
        health_events.append(event)

    bus.subscribe("system.health_changed", health_handler)
    await actions.start(bus)
    await supervisor.start()
    action = await actions.request_action(
        "speech.speak",
        {},
        resource="speaker",
        source_module="speech",
    )
    assert not isinstance(action, ActionRequestError)

    await supervisor._check_all_health()
    await bus.run_until_idle()
    await supervisor.stop()

    assert health_events[-1].payload == {"component": "speech", "status": "unavailable"}
    assert actions.get_action(action.action_id).status is ActionStatus.FAILED
    assert actions.get_action(action.action_id).error == {"reason": "module_crashed"}
