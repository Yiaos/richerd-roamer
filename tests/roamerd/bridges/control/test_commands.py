import pytest

from roamerd.bridges.control.commands import ControlCommandRouter
from roamerd.bridges.control.protocol import RequestEnvelope
from roamerd.events import Event
from roamerd.kernel import ActionManager, EventBus, PolicyEngine, StateManager, WorldModel


@pytest.mark.asyncio
async def test_control_router_ping_status_and_run_action() -> None:
    bus = EventBus()
    actions = ActionManager()
    state = StateManager(session_id="session-1")
    world = WorldModel()
    policy = PolicyEngine(session_id="session-1")
    await actions.start(bus)
    await state.start(bus)
    await policy.start(bus, actions, state, world)
    await bus.publish(
        Event(
            event_type="system.module_ready",
            source="test",
            session_id="session-1",
            payload={"module": "speech"},
        )
    )
    await bus.run_until_idle()
    router = ControlCommandRouter(
        event_bus=bus,
        action_manager=actions,
        policy_engine=policy,
        state_manager=state,
    )

    ping = await router.dispatch(RequestEnvelope(request_id="1", op="ping"))
    status = await router.dispatch(RequestEnvelope(request_id="2", op="status"))
    run = await router.dispatch(
        RequestEnvelope(
            request_id="3",
            op="run",
            args={"action": "speech.speak", "resource": "speaker", "payload": {"text": "hi"}},
            wait="accepted",
        )
    )

    assert ping.result["pong"] is True
    assert status.result["session_id"] == "session-1"
    assert run.action_id is not None

    session = await router.dispatch(
        RequestEnvelope(request_id="4", op="session.start", args={"kind": "voice_turn"})
    )
    assert session.result["kind"] == "voice_turn"


@pytest.mark.asyncio
async def test_control_router_action_status_and_list() -> None:
    bus = EventBus()
    actions = ActionManager()
    state = StateManager(session_id="session-1")
    policy = PolicyEngine(session_id="session-1")
    router = ControlCommandRouter(
        event_bus=bus,
        action_manager=actions,
        policy_engine=policy,
        state_manager=state,
    )
    await actions.start(bus)
    action = await actions.request_action("time.now", {}, resource="none")

    status = await router.dispatch(
        RequestEnvelope(request_id="1", op="action.status", args={"action_id": action.action_id})
    )
    listed = await router.dispatch(RequestEnvelope(request_id="2", op="actions.list"))
    cancel = await router.dispatch(
        RequestEnvelope(request_id="3", op="action.cancel", args={"action_id": action.action_id})
    )

    assert status.result["status"] == "running"
    assert listed.result["actions"][0]["action_id"] == action.action_id
    assert cancel.status == "ok"
    assert cancel.result["cancel_requested"] is True
