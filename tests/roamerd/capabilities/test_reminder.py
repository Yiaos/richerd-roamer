import asyncio

import pytest

from roamerd.capabilities.reminder import ReminderModule
from roamerd.events import Event
from roamerd.kernel import ActionManager, ActionRequestError, EventBus
from roamerd.kernel.action_manager import ActionStatus


@pytest.mark.asyncio
async def test_reminder_schedules_ack_and_due_speak_actions() -> None:
    bus = EventBus()
    actions = ActionManager()
    module = ReminderModule(action_manager=actions, session_id="session-1")
    started: list[Event] = []

    async def handler(event: Event) -> None:
        started.append(event)

    bus.subscribe("action.started", handler)
    await actions.start(bus)
    await module.start(bus)
    action = await actions.request_action(
        "remind.schedule",
        {"delay_sec": "0.02", "text": "喝水"},
        source_module="reminder",
    )
    assert not isinstance(action, ActionRequestError)

    await bus.run_until_idle()
    ack = [event for event in started if event.payload["action_type"] == "speech.speak"][0]
    await actions.complete_action(str(ack.payload["action_id"]), {"ok": True})
    await asyncio.sleep(0.04)
    await bus.run_until_idle()

    speak_payloads = [
        actions.get_action(str(event.payload["action_id"])).payload
        for event in started
        if event.payload["action_type"] == "speech.speak"
    ]
    assert speak_payloads == [{"text": "好的，0秒后提醒你喝水"}, {"text": "提醒：喝水"}]
    assert actions.get_action(action.action_id).result == {"scheduled": True, "delay_sec": 0.02}


@pytest.mark.asyncio
async def test_reminder_cancel_prevents_due_speak_action() -> None:
    bus = EventBus()
    actions = ActionManager()
    module = ReminderModule(action_manager=actions, session_id="session-1")
    started: list[Event] = []

    async def handler(event: Event) -> None:
        started.append(event)

    bus.subscribe("action.started", handler)
    await actions.start(bus)
    await module.start(bus)
    action = await actions.request_action(
        "remind.schedule",
        {"delay_sec": "0.05", "text": "喝水"},
        source_module="reminder",
    )
    assert not isinstance(action, ActionRequestError)
    await bus.run_until_idle()

    await actions.cancel_action(action.action_id, "user_cancel")
    await bus.run_until_idle()
    await asyncio.sleep(0.07)
    await bus.run_until_idle()

    due_speaks = [
        event
        for event in started
        if event.payload["action_type"] == "speech.speak"
        and actions.get_action(str(event.payload["action_id"])).payload == {"text": "提醒：喝水"}
    ]
    assert due_speaks == []
    assert actions.get_action(action.action_id).status is ActionStatus.CANCELLED


@pytest.mark.asyncio
async def test_reminder_is_non_persistent_across_restart() -> None:
    bus = EventBus()
    actions = ActionManager()
    module = ReminderModule(action_manager=actions, session_id="session-1")
    started: list[Event] = []

    async def handler(event: Event) -> None:
        started.append(event)

    bus.subscribe("action.started", handler)
    await actions.start(bus)
    await module.start(bus)
    action = await actions.request_action(
        "remind.schedule",
        {"delay_sec": "0.05", "text": "喝水"},
        source_module="reminder",
    )
    assert not isinstance(action, ActionRequestError)
    await bus.run_until_idle()
    await module.stop()
    restarted = ReminderModule(action_manager=actions, session_id="session-1")
    await restarted.start(bus)

    await asyncio.sleep(0.07)
    await bus.run_until_idle()

    assert all(
        actions.get_action(str(event.payload["action_id"])).payload != {"text": "提醒：喝水"}
        for event in started
        if event.payload["action_type"] == "speech.speak"
    )
