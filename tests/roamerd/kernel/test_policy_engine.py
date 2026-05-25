import pytest

from roamerd.config.schema import IntentConfig, PlaceConfig, RoamerdConfig
from roamerd.contracts.errors import ErrorCode
from roamerd.events import Event, Priority
from roamerd.kernel.action_manager import ActionManager, ActionRequestError, ActionStatus
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.policy_engine import ActionRequest, PolicyEngine, PolicyRuleStore
from roamerd.kernel.state_manager import StateManager
from roamerd.kernel.world_model import WorldModel


def make_event(event_type: str, payload: dict[str, object] | None = None) -> Event:
    return Event(
        event_type=event_type,
        source="test",
        session_id="session-1",
        priority=Priority.NORMAL,
        payload=payload or {},
    )


async def build_policy() -> tuple[EventBus, ActionManager, StateManager, WorldModel, PolicyEngine]:
    bus = EventBus()
    actions = ActionManager()
    state = StateManager(session_id="session-1")
    world = WorldModel(static_places={"客厅": PlaceConfig(x=10, y=20, angle=1)})
    policy = PolicyEngine(session_id="session-1")
    await actions.start(bus)
    await state.start(bus)
    await world.start(bus)
    await policy.start(bus, actions, state, world)
    for module in ("motion", "speech", "camera", "body"):
        await bus.publish(make_event("system.module_ready", {"module": module}))
    await bus.run_until_idle()
    return bus, actions, state, world, policy


def test_match_local_intent_extracts_slots_and_defaults() -> None:
    policy = PolicyEngine(session_id="session-1")

    goto = policy.match_local_intent("去客厅")
    reminder = policy.match_local_intent("5分钟后提醒我")
    miss = policy.match_local_intent("给我讲个笑话")

    assert goto.matched is True
    assert goto.action_type == "motion.goto"
    assert goto.slots == {"location": "客厅"}
    assert reminder.action_type == "remind.schedule"
    assert reminder.slots == {"delay_sec": "300", "text": "提醒"}
    assert miss.matched is False
    assert miss.reason == "no_intent_match"


def test_policy_rule_store_loads_local_intents_from_config() -> None:
    store = PolicyRuleStore.from_config(
        [
            IntentConfig(
                name="custom_ping",
                action="time.now",
                patterns=["报时"],
                priority=Priority.NORMAL,
            )
        ]
    )
    policy = PolicyEngine(session_id="session-1", rules=store)

    assert policy.match_local_intent("请报时").intent_name == "custom_ping"


@pytest.mark.asyncio
async def test_transcript_local_motion_intent_creates_action_without_cognition() -> None:
    bus, actions, _, _, _ = await build_policy()
    cognition_events: list[Event] = []

    async def cognition_handler(event: Event) -> None:
        cognition_events.append(event)

    bus.subscribe("cognition.request_needed", cognition_handler)
    await bus.publish(make_event("hearing.transcript_ready", {"text": "回去充电"}))
    await bus.run_until_idle()

    running = actions.get_running_actions("motion")
    assert [action.action_type for action in running] == ["motion.home"]
    assert cognition_events == []


@pytest.mark.asyncio
async def test_goto_local_intent_resolves_world_place_into_payload() -> None:
    bus, actions, _, _, _ = await build_policy()

    await bus.publish(make_event("hearing.transcript_ready", {"text": "去客厅"}))
    await bus.run_until_idle()

    [action] = actions.get_running_actions("motion")
    assert action.action_type == "motion.goto"
    assert action.payload["target"] == {"name": "客厅", "x": 10.0, "y": 20.0, "angle": 1.0}


@pytest.mark.asyncio
async def test_local_intent_miss_routes_to_cognition() -> None:
    bus, _, _, _, _ = await build_policy()
    cognition_events: list[Event] = []

    async def cognition_handler(event: Event) -> None:
        cognition_events.append(event)

    bus.subscribe("cognition.request_needed", cognition_handler)
    await bus.publish(make_event("hearing.transcript_ready", {"text": "你觉得我该休息吗"}))
    await bus.run_until_idle()

    assert cognition_events[0].payload["text"] == "你觉得我该休息吗"


@pytest.mark.asyncio
async def test_safety_text_preempts_motion_without_cognition() -> None:
    bus, actions, _, _, _ = await build_policy()
    action = await actions.request_action(
        "motion.goto",
        {},
        resource="motion",
        source_module="motion",
    )
    assert not isinstance(action, ActionRequestError)

    await bus.publish(make_event("hearing.transcript_ready", {"text": "停"}))
    await bus.run_until_idle()

    assert actions.get_action(action.action_id).status is ActionStatus.PREEMPTING


@pytest.mark.asyncio
async def test_admission_rejects_unknown_action_and_unavailable_module() -> None:
    bus, _, state, world, policy = await build_policy()

    unknown = await policy.admit_action(
        ActionRequest(action_type="shell.exec", payload={}, resource="none", source="test")
    )
    assert unknown.admitted is False
    assert unknown.error_code is ErrorCode.CONVERSE_INTENT_INVALID_ACTION

    await bus.publish(
        make_event("system.health_changed", {"component": "motion", "status": "unavailable"})
    )
    await bus.run_until_idle()
    rejected = await policy.admit_action(
        ActionRequest(action_type="motion.home", payload={}, resource="motion", source="test")
    )

    assert state.get_module_health("motion").value == "unavailable"
    assert world.resolve_place("客厅") is not None
    assert rejected.admitted is False
    assert rejected.reason == "motion module unavailable"


@pytest.mark.asyncio
async def test_cognition_response_action_request_is_admitted() -> None:
    bus, actions, _, _, _ = await build_policy()

    await bus.publish(
        make_event(
            "cognition.response_received",
            {
                "kind": "action",
                "action_request": {
                    "action_type": "speech.speak",
                    "resource": "speaker",
                    "payload": {"text": "好的"},
                    "source": "cognition_bridge",
                },
            },
        )
    )
    await bus.run_until_idle()

    [action] = actions.get_running_actions("speaker")
    assert action.action_type == "speech.speak"
    assert action.payload == {"text": "好的"}


@pytest.mark.asyncio
async def test_control_command_received_is_admitted() -> None:
    bus, actions, _, _, _ = await build_policy()

    await bus.publish(
        make_event(
            "control.command_received",
            {
                "action_request": {
                    "action_type": "speech.speak",
                    "resource": "speaker",
                    "payload": {"text": "hi"},
                    "source": "control_bridge",
                },
            },
        )
    )
    await bus.run_until_idle()

    [action] = actions.get_running_actions("speaker")
    assert action.action_type == "speech.speak"
    assert action.payload == {"text": "hi"}


@pytest.mark.asyncio
async def test_memory_policy_update_replaces_local_intent_catalog() -> None:
    bus, actions, _, _, policy = await build_policy()

    await bus.publish(
        make_event(
            "memory.policy_update",
            {
                "local_intents": [
                    {
                        "name": "custom_say_hi",
                        "action": "speech.speak",
                        "patterns": ["打招呼"],
                        "priority": "normal",
                    }
                ]
            },
        )
    )
    await bus.run_until_idle()

    match = policy.match_local_intent("请打招呼")
    assert match.intent_name == "custom_say_hi"

    await bus.publish(make_event("hearing.transcript_ready", {"text": "请打招呼"}))
    await bus.run_until_idle()

    [action] = actions.get_running_actions("speaker")
    assert action.action_type == "speech.speak"


@pytest.mark.asyncio
async def test_resource_busy_high_priority_request_preempts_lower_priority_action() -> None:
    bus, actions, _, _, policy = await build_policy()
    low = await actions.request_action(
        "speech.speak",
        {"text": "low"},
        resource="speaker",
        priority=Priority.LOW,
        source_module="speech",
    )
    assert not isinstance(low, ActionRequestError)

    decision = await policy.admit_action(
        ActionRequest(
            action_type="speech.speak",
            payload={"text": "urgent"},
            resource="speaker",
            priority=Priority.HIGH,
            source="test",
        )
    )

    assert decision.decision_type == "preempt"
    assert decision.admitted is True
    assert decision.preempted == [low.action_id]
    assert actions.get_action(low.action_id).status is ActionStatus.PREEMPTING


@pytest.mark.asyncio
async def test_wake_triggered_while_speaking_is_ignored() -> None:
    bus, _, state, _, _ = await build_policy()
    listen_events: list[Event] = []

    async def handler(event: Event) -> None:
        listen_events.append(event)

    bus.subscribe("hearing.listen_requested", handler)
    await bus.publish(make_event("speech.playback_started"))
    await bus.publish(make_event("hearing.wake_triggered"))
    await bus.run_until_idle()

    assert state.is_speaking is True
    assert listen_events == []


@pytest.mark.asyncio
async def test_wake_triggered_while_idle_requests_listen() -> None:
    bus, _, _, _, _ = await build_policy()
    listen_events: list[Event] = []

    async def handler(event: Event) -> None:
        listen_events.append(event)

    bus.subscribe("hearing.listen_requested", handler)
    await bus.publish(make_event("hearing.wake_triggered", {"wakeword": "test"}))
    await bus.run_until_idle()

    assert listen_events[0].payload == {"wakeword": "test"}


@pytest.mark.asyncio
async def test_cognition_unavailable_complex_text_creates_polite_speech() -> None:
    bus, actions, _, _, _ = await build_policy()
    await bus.publish(make_event("cognition.unavailable", {"reason": "timeout"}))
    await bus.run_until_idle()

    await bus.publish(make_event("hearing.transcript_ready", {"text": "给我讲个笑话"}))
    await bus.run_until_idle()

    [action] = actions.get_running_actions("speaker")
    assert action.action_type == "speech.speak"
    assert "暂时" in str(action.payload["text"])


def test_create_app_uses_policy_config_for_intent_catalog() -> None:
    from roamerd.app import create_app

    app = create_app(
        RoamerdConfig.model_validate(
            {
                "policy": {
                    "local_intents": [
                        {
                            "name": "custom_ping",
                            "action": "time.now",
                            "patterns": ["报时"],
                        }
                    ]
                }
            }
        )
    )

    assert app.policy_engine.match_local_intent("现在报时").intent_name == "custom_ping"


def test_create_app_uses_logging_config(tmp_path) -> None:
    from roamerd.app import create_app

    app = create_app(
        RoamerdConfig.model_validate(
            {"logging": {"dir": str(tmp_path), "log_transcripts": False, "log_audio_paths": False}}
        )
    )

    try:
        assert app.observability.log_dir == tmp_path
    finally:
        app.observability.close()
