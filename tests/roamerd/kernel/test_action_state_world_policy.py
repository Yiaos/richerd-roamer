import asyncio

from roamerd.bridges.control.bridge import ControlBridge
from roamerd.compat.legacy_config import load_config
from roamerd.contracts.action import ActionRequest, PreemptionScope
from roamerd.events import Priority, make_event
from roamerd.events.control import ControlCommandPayload
from roamerd.kernel.action_manager import ActionManager
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.policy_engine import PolicyEngine
from roamerd.kernel.state_manager import StateManager
from roamerd.kernel.world_model import PersonPresence, WorldModel


def test_action_manager_resource_lock_and_lifecycle() -> None:
    async def scenario() -> str:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        await actions.start(bus)
        action = await actions.request_action("speak", {"text": "hi"}, resource="speaker")
        await actions.complete_action(action.action_id, {"ok": True})
        return actions.get_action(action.action_id).status.value  # type: ignore[union-attr]

    assert asyncio.run(scenario()) == "completed"


def test_action_manager_fails_running_action_when_module_becomes_unavailable() -> None:
    async def scenario() -> tuple[str, dict[str, object]]:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        await actions.start(bus)
        action = await actions.request_action("speak", {"text": "hi"}, resource="speaker")
        await bus.publish(
            make_event(
                "system.health_changed",
                source="supervisor",
                session_id="s",
                payload={
                    "name": "speaker",
                    "component_type": "module",
                    "state": "unavailable",
                },
            )
        )
        await bus.drain_once()
        failed = actions.get_action(action.action_id)
        assert failed is not None
        return failed.status.value, failed.error or {}

    assert asyncio.run(scenario()) == (
        "failed",
        {"error_code": "module_crashed", "error_message": "speaker module unavailable"},
    )


def test_action_manager_terminal_lifecycle_events_include_action_metadata() -> None:
    async def scenario() -> list[dict[str, object]]:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        await actions.start(bus)
        events: list[dict[str, object]] = []

        async def handler(event):
            events.append(event.payload)

        bus.subscribe("action.cancelled", handler)
        bus.subscribe("action.preempted", handler)
        cancelled = await actions.request_action("speak", {"text": "stop me"}, resource="speaker")
        await actions.cancel_action(cancelled.action_id, "client_request")
        moving = await actions.request_action(
            "motion.goto", {"target": {"x": 1, "y": 2}}, resource="motion"
        )
        preempted_ids = await actions.preempt(
            PreemptionScope(target_resources=["motion"], reason="safety", source_event="evt-1")
        )
        await bus.drain_once()
        assert preempted_ids == [moving.action_id]
        return sorted(events, key=lambda item: str(item.get("action_type", "")))

    assert asyncio.run(scenario()) == [
        {
            "action_type": "motion.goto",
            "resource": "motion",
            "priority": "normal",
            "payload": {"target": {"x": 1, "y": 2}},
            "reason": "safety",
            "source_event": "evt-1",
        },
        {
            "action_type": "speak",
            "resource": "speaker",
            "priority": "normal",
            "payload": {"text": "stop me"},
            "reason": "client_request",
        },
    ]


def test_state_manager_updates_from_events() -> None:
    async def scenario() -> bool:
        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        await state.start(bus)
        await bus.publish(make_event("speech.playback_started", source="t", session_id="s"))
        await bus.drain_once()
        return state.snapshot().audio.playback_active

    assert asyncio.run(scenario()) is True


def test_state_manager_clears_active_io_on_cancelled_actions() -> None:
    async def scenario() -> tuple[bool, bool, bool]:
        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        await state.start(bus)
        await bus.publish(make_event("hearing.recording_started", source="t", session_id="s"))
        await bus.publish(make_event("speech.playback_started", source="t", session_id="s"))
        await bus.publish(make_event("motion.started", source="t", session_id="s"))
        await bus.drain_once()
        await bus.publish(
            make_event(
                "action.cancelled",
                source="t",
                session_id="s",
                payload={"action_type": "listen"},
            )
        )
        await bus.publish(
            make_event(
                "action.cancelled",
                source="t",
                session_id="s",
                payload={"action_type": "speak"},
            )
        )
        await bus.publish(
            make_event(
                "action.cancelled",
                source="t",
                session_id="s",
                payload={"action_type": "motion.goto"},
            )
        )
        await bus.drain_once()
        snapshot = state.snapshot()
        return (
            snapshot.audio.listening,
            snapshot.audio.playback_active,
            snapshot.motion.moving,
        )

    assert asyncio.run(scenario()) == (False, False, False)


def test_world_model_resolves_migrated_named_point() -> None:
    config = load_config()
    world = WorldModel(config.world_model)
    place = world.resolve_place("阳台")
    assert place is not None
    assert place.pose.x == 2082


def test_world_model_merges_later_person_name_for_same_embedding() -> None:
    async def scenario() -> list[PersonPresence]:
        config = load_config()
        bus = EventBus(session_id="s")
        world = WorldModel(config.world_model)
        await world.start(bus)
        await bus.publish(
            make_event(
                "vision.person_detected",
                source="test",
                session_id="s",
                payload={"embedding_id": "person-1", "confidence": 0.4},
            )
        )
        await bus.drain_once()
        await bus.publish(
            make_event(
                "vision.person_detected",
                source="test",
                session_id="s",
                payload={
                    "embedding_id": "person-1",
                    "name": "Richer",
                    "confidence": 0.9,
                },
            )
        )
        await bus.drain_once()
        return world.get_people_present()

    people = asyncio.run(scenario())
    assert len(people) == 1
    assert people[0].person_id == "person-1"
    assert people[0].name == "Richer"
    assert people[0].identity_confidence == 0.9


def test_policy_local_intent_creates_home_action() -> None:
    async def scenario() -> list[str]:
        config = load_config()
        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        actions = ActionManager(session_id="s")
        world = WorldModel(config.world_model)
        policy = PolicyEngine(
            session_id="s", config=config.policy, state=state, actions=actions, world=world
        )
        await state.start(bus)
        await actions.start(bus)
        await world.start(bus)
        await policy.start(bus)
        await bus.publish(
            make_event(
                "system.module_ready",
                source="t",
                session_id="s",
                payload={"name": "motion", "component_type": "module", "state": "healthy"},
            )
        )
        await bus.drain_once()
        await bus.publish(
            make_event(
                "hearing.transcript_ready",
                source="t",
                session_id="s",
                payload={"text": "回充电"},
                priority=Priority.HIGH,
            )
        )
        await bus.drain_once()
        return [action.action_type for action in actions.get_running_actions()]

    assert "motion.home" in asyncio.run(scenario())


def test_policy_ignores_non_stop_wake_command_while_speaking() -> None:
    async def scenario() -> list[dict[str, object]]:
        config = load_config()
        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        actions = ActionManager(session_id="s")
        world = WorldModel(config.world_model)
        policy = PolicyEngine(
            session_id="s", config=config.policy, state=state, actions=actions, world=world
        )
        matched: list[dict[str, object]] = []

        async def handler(event):
            matched.append(event.payload)

        bus.subscribe("policy.local_intent_matched", handler)
        await state.start(bus)
        await actions.start(bus)
        await policy.start(bus)
        await bus.publish(make_event("speech.playback_started", source="test", session_id="s"))
        await bus.drain_once()
        await bus.publish(
            make_event(
                "hearing.wake_triggered",
                source="test",
                session_id="s",
                payload={"source": "su03t_gpio", "command_text": "回充电"},
            )
        )
        await bus.drain_once()
        return matched

    assert asyncio.run(scenario()) == []


def test_policy_allows_stop_phrase_wake_command_while_speaking() -> None:
    async def scenario() -> list[dict[str, object]]:
        config = load_config()
        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        actions = ActionManager(session_id="s")
        world = WorldModel(config.world_model)
        policy = PolicyEngine(
            session_id="s", config=config.policy, state=state, actions=actions, world=world
        )
        safety: list[dict[str, object]] = []

        async def handler(event):
            safety.append(event.payload)

        bus.subscribe("safety.emergency_stop_requested", handler)
        await state.start(bus)
        await actions.start(bus)
        await policy.start(bus)
        await bus.publish(make_event("speech.playback_started", source="test", session_id="s"))
        await bus.drain_once()
        await bus.publish(
            make_event(
                "hearing.wake_triggered",
                source="test",
                session_id="s",
                payload={"source": "su03t_gpio", "command_text": "停"},
            )
        )
        await bus.drain_once()
        return safety

    assert asyncio.run(scenario()) == [{"reason": "local_voice"}]


def test_policy_strips_wake_phrase_before_routing_command_text() -> None:
    async def scenario() -> list[str]:
        config = load_config()
        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        actions = ActionManager(session_id="s")
        world = WorldModel(config.world_model)
        policy = PolicyEngine(
            session_id="s", config=config.policy, state=state, actions=actions, world=world
        )
        routed: list[str] = []

        async def handler(event):
            routed.append(str(event.payload.get("text")))

        bus.subscribe("cognition.request_needed", handler)
        await state.start(bus)
        await actions.start(bus)
        await policy.start(bus)
        await bus.publish(
            make_event(
                "hearing.wake_triggered",
                source="test",
                session_id="s",
                payload={
                    "source": "su03t_gpio",
                    "phrase": "Richard",
                    "command_text": "Richard 帮我查天气",
                },
            )
        )
        await bus.drain_once()
        await bus.drain_once()
        return routed

    assert asyncio.run(scenario()) == ["帮我查天气"]


def test_policy_strips_compact_ascii_wake_phrase_before_routing_command_text() -> None:
    async def scenario() -> list[str]:
        config = load_config()
        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        actions = ActionManager(session_id="s")
        world = WorldModel(config.world_model)
        policy = PolicyEngine(
            session_id="s", config=config.policy, state=state, actions=actions, world=world
        )
        routed: list[str] = []

        async def handler(event):
            routed.append(str(event.payload.get("text")))

        bus.subscribe("cognition.request_needed", handler)
        await state.start(bus)
        await actions.start(bus)
        await policy.start(bus)
        await bus.publish(
            make_event(
                "hearing.wake_triggered",
                source="test",
                session_id="s",
                payload={
                    "source": "su03t_gpio",
                    "command_text": "rich-erd 帮我查天气",
                },
            )
        )
        await bus.drain_once()
        await bus.drain_once()
        return routed

    assert asyncio.run(scenario()) == ["帮我查天气"]


def test_policy_strips_chinese_wake_phrase_without_separator() -> None:
    async def scenario() -> list[str]:
        config = load_config()
        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        actions = ActionManager(session_id="s")
        world = WorldModel(config.world_model)
        policy = PolicyEngine(
            session_id="s", config=config.policy, state=state, actions=actions, world=world
        )
        routed: list[str] = []

        async def handler(event):
            routed.append(str(event.payload.get("text")))

        bus.subscribe("cognition.request_needed", handler)
        await state.start(bus)
        await actions.start(bus)
        await policy.start(bus)
        await bus.publish(
            make_event(
                "hearing.wake_triggered",
                source="test",
                session_id="s",
                payload={
                    "source": "su03t_gpio",
                    "command_text": "瑞彻德帮我查天气",
                },
            )
        )
        await bus.drain_once()
        await bus.drain_once()
        return routed

    assert asyncio.run(scenario()) == ["帮我查天气"]


def test_policy_wake_phrase_only_starts_listen_without_routing() -> None:
    async def scenario() -> tuple[list[str], list[str]]:
        config = load_config()
        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        actions = ActionManager(session_id="s")
        world = WorldModel(config.world_model)
        policy = PolicyEngine(
            session_id="s", config=config.policy, state=state, actions=actions, world=world
        )
        routed: list[str] = []

        async def handler(event):
            routed.append(str(event.payload.get("text")))

        bus.subscribe("cognition.request_needed", handler)
        await state.start(bus)
        await actions.start(bus)
        await policy.start(bus)
        await bus.publish(
            make_event(
                "system.module_ready",
                source="test",
                session_id="s",
                payload={"name": "microphone", "component_type": "module", "state": "healthy"},
            )
        )
        await bus.drain_once()
        await bus.publish(
            make_event(
                "hearing.wake_triggered",
                source="test",
                session_id="s",
                payload={
                    "source": "su03t_gpio",
                    "phrase": "Richard",
                    "command_text": "Richard",
                },
            )
        )
        await bus.drain_once()
        running = [action.action_type for action in actions.get_running_actions()]
        return routed, running

    assert asyncio.run(scenario()) == ([], ["listen"])


def test_policy_wake_phrase_only_listen_uses_followup_timeout() -> None:
    async def scenario() -> dict[str, object]:
        config = load_config()
        config.policy.local_voice.followup_timeout_sec = 3.0
        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        actions = ActionManager(session_id="s")
        world = WorldModel(config.world_model)
        policy = PolicyEngine(
            session_id="s",
            config=config.policy,
            state=state,
            actions=actions,
            world=world,
            clock=lambda: 100.0,
        )
        await state.start(bus)
        await actions.start(bus)
        await policy.start(bus)
        await bus.publish(
            make_event(
                "system.module_ready",
                source="test",
                session_id="s",
                payload={"name": "microphone", "component_type": "module", "state": "healthy"},
            )
        )
        await bus.drain_once()
        await bus.publish(
            make_event(
                "hearing.wake_triggered",
                source="test",
                session_id="s",
                payload={
                    "source": "su03t_gpio",
                    "phrase": "Richard",
                    "command_text": "Richard",
                },
            )
        )
        await bus.drain_once()
        running = actions.get_running_actions()
        assert len(running) == 1
        return running[0].payload

    assert asyncio.run(scenario()) == {"pre_roll_sec": 1.0, "timeout": 3.0}


def test_policy_wake_listen_includes_preroll_seconds() -> None:
    async def scenario() -> dict[str, object]:
        config = load_config()
        config.policy.local_voice.pre_roll_sec = 1.0
        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        actions = ActionManager(session_id="s")
        world = WorldModel(config.world_model)
        policy = PolicyEngine(
            session_id="s", config=config.policy, state=state, actions=actions, world=world
        )
        await state.start(bus)
        await actions.start(bus)
        await policy.start(bus)
        await bus.publish(
            make_event(
                "system.module_ready",
                source="test",
                session_id="s",
                payload={"name": "microphone", "component_type": "module", "state": "healthy"},
            )
        )
        await bus.drain_once()
        await bus.publish(
            make_event(
                "hearing.wake_triggered",
                source="test",
                session_id="s",
                payload={"source": "su03t_gpio"},
            )
        )
        await bus.drain_once()
        running = actions.get_running_actions()
        assert len(running) == 1
        return running[0].payload

    assert asyncio.run(scenario()) == {"pre_roll_sec": 1.0}


def test_policy_followup_listen_uses_remaining_timeout() -> None:
    async def scenario() -> list[dict[str, object]]:
        config = load_config()
        config.policy.local_voice.followup_timeout_sec = 3.0
        now = {"value": 100.0}

        def clock() -> float:
            return now["value"]

        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        actions = ActionManager(session_id="s")
        world = WorldModel(config.world_model)
        policy = PolicyEngine(
            session_id="s",
            config=config.policy,
            state=state,
            actions=actions,
            world=world,
            clock=clock,
        )
        await state.start(bus)
        await actions.start(bus)
        await policy.start(bus)
        await bus.publish(
            make_event(
                "system.module_ready",
                source="test",
                session_id="s",
                payload={"name": "microphone", "component_type": "module", "state": "healthy"},
            )
        )
        await bus.drain_once()
        await bus.publish(
            make_event(
                "hearing.wake_triggered",
                source="test",
                session_id="s",
                payload={"source": "su03t_gpio", "command_text": "Richard"},
            )
        )
        await bus.drain_once()
        first = actions.get_running_actions()[0]
        await actions.cancel_action(first.action_id, "test")
        now["value"] = 101.0
        await bus.publish(
            make_event(
                "hearing.wake_triggered",
                source="test",
                session_id="s",
                payload={"source": "su03t_gpio"},
            )
        )
        await bus.drain_once()
        running = actions.get_running_actions()
        return [first.payload, running[0].payload]

    assert asyncio.run(scenario()) == [
        {"pre_roll_sec": 1.0, "timeout": 3.0},
        {"pre_roll_sec": 1.0, "timeout": 2.0},
    ]


def test_policy_stop_phrase_in_followup_exits_without_routing() -> None:
    async def scenario() -> tuple[list[dict[str, object]], list[str], list[dict[str, object]]]:
        config = load_config()
        config.policy.local_voice.followup_timeout_sec = 3.0
        now = {"value": 100.0}

        def clock() -> float:
            return now["value"]

        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        actions = ActionManager(session_id="s")
        world = WorldModel(config.world_model)
        policy = PolicyEngine(
            session_id="s",
            config=config.policy,
            state=state,
            actions=actions,
            world=world,
            clock=clock,
        )
        safety: list[dict[str, object]] = []
        routed: list[str] = []

        async def safety_handler(event):
            safety.append(event.payload)

        async def cognition_handler(event):
            routed.append(str(event.payload.get("text")))

        bus.subscribe("safety.emergency_stop_requested", safety_handler)
        bus.subscribe("cognition.request_needed", cognition_handler)
        await state.start(bus)
        await actions.start(bus)
        await policy.start(bus)
        await bus.publish(
            make_event(
                "system.module_ready",
                source="test",
                session_id="s",
                payload={"name": "microphone", "component_type": "module", "state": "healthy"},
            )
        )
        await bus.drain_once()
        await bus.publish(
            make_event(
                "hearing.wake_triggered",
                source="test",
                session_id="s",
                payload={"source": "su03t_gpio", "command_text": "Richard"},
            )
        )
        await bus.drain_once()
        first = actions.get_running_actions()[0]
        await actions.cancel_action(first.action_id, "test")
        await bus.publish(
            make_event(
                "hearing.transcript_ready",
                source="test",
                session_id="s",
                payload={"text": "不用了"},
            )
        )
        await bus.drain_once()
        await bus.publish(
            make_event(
                "hearing.wake_triggered",
                source="test",
                session_id="s",
                payload={"source": "su03t_gpio"},
            )
        )
        await bus.drain_once()
        running = [action.payload for action in actions.get_running_actions()]
        return safety, routed, running

    assert asyncio.run(scenario()) == ([], [], [{"pre_roll_sec": 1.0}])


def test_policy_max_followup_turns_exits_after_routed_followup_command() -> None:
    async def scenario() -> tuple[list[str], list[dict[str, object]]]:
        config = load_config()
        config.policy.local_voice.followup_timeout_sec = 3.0
        config.policy.local_voice.max_followup_turns = 1
        now = {"value": 100.0}

        def clock() -> float:
            return now["value"]

        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        actions = ActionManager(session_id="s")
        world = WorldModel(config.world_model)
        policy = PolicyEngine(
            session_id="s",
            config=config.policy,
            state=state,
            actions=actions,
            world=world,
            clock=clock,
        )
        routed: list[str] = []

        async def cognition_handler(event):
            routed.append(str(event.payload.get("text")))

        bus.subscribe("cognition.request_needed", cognition_handler)
        await state.start(bus)
        await actions.start(bus)
        await policy.start(bus)
        await bus.publish(
            make_event(
                "system.module_ready",
                source="test",
                session_id="s",
                payload={"name": "microphone", "component_type": "module", "state": "healthy"},
            )
        )
        await bus.drain_once()
        await bus.publish(
            make_event(
                "hearing.wake_triggered",
                source="test",
                session_id="s",
                payload={"source": "su03t_gpio", "command_text": "Richard"},
            )
        )
        await bus.drain_once()
        first = actions.get_running_actions()[0]
        await actions.cancel_action(first.action_id, "test")
        await bus.publish(
            make_event(
                "hearing.transcript_ready",
                source="test",
                session_id="s",
                payload={"text": "帮我查天气"},
            )
        )
        await bus.drain_once()
        await bus.drain_once()
        await bus.publish(
            make_event(
                "hearing.wake_triggered",
                source="test",
                session_id="s",
                payload={"source": "su03t_gpio"},
            )
        )
        await bus.drain_once()
        running = [action.payload for action in actions.get_running_actions()]
        return routed, running

    assert asyncio.run(scenario()) == (["帮我查天气"], [{"pre_roll_sec": 1.0}])


def test_policy_playback_completed_reopens_armed_followup_window() -> None:
    async def scenario() -> tuple[list[str], list[dict[str, object]]]:
        config = load_config()
        config.policy.local_voice.followup_timeout_sec = 3.0
        now = {"value": 100.0}

        def clock() -> float:
            return now["value"]

        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        actions = ActionManager(session_id="s")
        world = WorldModel(config.world_model)
        policy = PolicyEngine(
            session_id="s",
            config=config.policy,
            state=state,
            actions=actions,
            world=world,
            clock=clock,
        )
        routed: list[str] = []

        async def cognition_handler(event):
            routed.append(str(event.payload.get("text")))

        bus.subscribe("cognition.request_needed", cognition_handler)
        await state.start(bus)
        await actions.start(bus)
        await policy.start(bus)
        for name in ("speaker", "microphone"):
            await bus.publish(
                make_event(
                    "system.module_ready",
                    source="test",
                    session_id="s",
                    payload={"name": name, "component_type": "module", "state": "healthy"},
                )
            )
        await bus.drain_once()
        await bus.publish(
            make_event(
                "cognition.response_received",
                source="test",
                session_id="s",
                payload={
                    "correlation_id": "c1",
                    "response_type": "speak",
                    "text": "可以",
                },
            )
        )
        await bus.drain_once()
        await bus.publish(
            make_event(
                "speech.playback_completed",
                source="test",
                session_id="s",
                payload={"action_id": "speak-1", "duration_sec": 0.5},
            )
        )
        await bus.drain_once()
        await bus.publish(
            make_event(
                "hearing.wake_triggered",
                source="test",
                session_id="s",
                payload={"source": "su03t_gpio"},
            )
        )
        await bus.drain_once()
        running = [action.payload for action in actions.get_running_actions()]
        return routed, running

    assert asyncio.run(scenario()) == (
        [],
        [{"text": "可以"}, {"pre_roll_sec": 1.0, "timeout": 3.0}],
    )


def test_policy_rejects_unknown_action() -> None:
    async def scenario() -> str:
        config = load_config()
        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        actions = ActionManager(session_id="s")
        world = WorldModel(config.world_model)
        policy = PolicyEngine(
            session_id="s", config=config.policy, state=state, actions=actions, world=world
        )
        await policy.start(bus)
        decision = await policy.admit_action(ActionRequest(action_type="unsafe", source="test"))
        return decision.reason

    assert asyncio.run(scenario()) == "action_not_allowed"


def test_policy_returns_structured_error_for_unknown_control_action_cancel() -> None:
    async def scenario() -> dict[str, object]:
        config = load_config()
        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        actions = ActionManager(session_id="s")
        world = WorldModel(config.world_model)
        policy = PolicyEngine(
            session_id="s", config=config.policy, state=state, actions=actions, world=world
        )
        control = ControlBridge(session_id="s")
        await policy.start(bus)
        await control.start(bus)
        bus.start_background()
        response = await control.request(
            ControlCommandPayload(
                op="action.cancel",
                args={"action_id": "missing-action"},
                request_id="cancel-1",
                timeout_ms=100,
                correlation_id="corr-cancel-1",
            )
        )
        await bus.stop()
        return response

    assert asyncio.run(scenario()) == {
        "correlation_id": "corr-cancel-1",
        "request_id": "cancel-1",
        "ok": False,
        "result": {"action_id": "missing-action", "state": "not_found"},
        "error_code": "action.not_found",
        "error_message": "Unknown action: missing-action",
    }


def test_control_action_status_op_returns_requested_action() -> None:
    async def scenario() -> dict[str, object]:
        config = load_config()
        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        actions = ActionManager(session_id="s")
        world = WorldModel(config.world_model)
        policy = PolicyEngine(
            session_id="s", config=config.policy, state=state, actions=actions, world=world
        )
        control = ControlBridge(session_id="s")
        await actions.start(bus)
        await policy.start(bus)
        await control.start(bus)
        action = await actions.request_action("sense", {}, resource="none")
        bus.start_background()
        try:
            response = await control.request(
                ControlCommandPayload(
                    op="action.status",
                    args={"action_id": action.action_id},
                    request_id="status-1",
                    timeout_ms=100,
                    correlation_id="corr-status-1",
                )
            )
            return response
        finally:
            await bus.stop()

    response = asyncio.run(scenario())
    assert response["ok"] is True
    assert response["request_id"] == "status-1"
    result = response["result"]
    assert isinstance(result, dict)
    action = result["action"]
    assert isinstance(action, dict)
    assert action["action_type"] == "sense"
    assert action["status"] == "running"


def test_control_resource_busy_rejection_is_retryable() -> None:
    async def scenario() -> dict[str, object]:
        config = load_config()
        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        actions = ActionManager(session_id="s")
        world = WorldModel(config.world_model)
        policy = PolicyEngine(
            session_id="s", config=config.policy, state=state, actions=actions, world=world
        )
        control = ControlBridge(session_id="s")
        await state.start(bus)
        await actions.start(bus)
        await policy.start(bus)
        await control.start(bus)
        bus.start_background()
        try:
            await bus.publish(
                make_event(
                    "system.module_ready",
                    source="test",
                    session_id="s",
                    payload={"name": "speaker", "component_type": "module", "state": "healthy"},
                )
            )
            await bus.drain_once()
            first = await control.request(
                ControlCommandPayload(
                    op="run",
                    action="speak",
                    args={"text": "first"},
                    timeout_ms=100,
                    correlation_id="first",
                )
            )
            assert first["ok"] is True
            second = await control.request(
                ControlCommandPayload(
                    op="run",
                    action="speak",
                    args={"text": "second"},
                    timeout_ms=100,
                    correlation_id="second",
                )
            )
            return second
        finally:
            await bus.stop()

    assert asyncio.run(scenario()) == {
        "correlation_id": "second",
        "ok": False,
        "result": {"action_id": "", "state": "rejected", "retryable": True},
        "error_code": "policy.rejected",
        "error_message": "resource_busy",
        "retryable": True,
    }


def test_control_motion_goto_location_resolves_named_point() -> None:
    async def scenario() -> dict[str, object]:
        config = load_config()
        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        actions = ActionManager(session_id="s")
        world = WorldModel(config.world_model)
        policy = PolicyEngine(
            session_id="s", config=config.policy, state=state, actions=actions, world=world
        )
        control = ControlBridge(session_id="s")
        await state.start(bus)
        await actions.start(bus)
        await policy.start(bus)
        await control.start(bus)
        bus.start_background()
        try:
            await bus.publish(
                make_event(
                    "system.module_ready",
                    source="test",
                    session_id="s",
                    payload={"name": "motion", "component_type": "module", "state": "healthy"},
                )
            )
            await bus.drain_once()
            response = await control.request(
                ControlCommandPayload(
                    op="run",
                    action="motion.goto",
                    args={"location": "阳台", "wait": False},
                    timeout_ms=100,
                    correlation_id="goto-location",
                )
            )
            assert response["ok"] is True
            running = actions.get_running_actions(resource="motion")
            return running[0].payload
        finally:
            await bus.stop()

    assert asyncio.run(scenario()) == {
        "location": "阳台",
        "wait": False,
        "target": {"x": 2082.0, "y": 2377.0, "angle": 111.0, "frame": "valetudo_pixel"},
    }


def test_control_motion_goto_location_angle_overrides_named_point_heading() -> None:
    async def scenario() -> dict[str, object]:
        config = load_config()
        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        actions = ActionManager(session_id="s")
        world = WorldModel(config.world_model)
        policy = PolicyEngine(
            session_id="s", config=config.policy, state=state, actions=actions, world=world
        )
        control = ControlBridge(session_id="s")
        await state.start(bus)
        await actions.start(bus)
        await policy.start(bus)
        await control.start(bus)
        bus.start_background()
        try:
            await bus.publish(
                make_event(
                    "system.module_ready",
                    source="test",
                    session_id="s",
                    payload={"name": "motion", "component_type": "module", "state": "healthy"},
                )
            )
            await bus.drain_once()
            response = await control.request(
                ControlCommandPayload(
                    op="run",
                    action="motion.goto",
                    args={"location": "阳台", "angle": 90.0, "wait": False},
                    timeout_ms=100,
                    correlation_id="goto-location-angle",
                )
            )
            assert response["ok"] is True
            running = actions.get_running_actions(resource="motion")
            target = running[0].payload["target"]
            assert isinstance(target, dict)
            return target
        finally:
            await bus.stop()

    assert asyncio.run(scenario()) == {
        "x": 2082.0,
        "y": 2377.0,
        "angle": 90.0,
        "frame": "valetudo_pixel",
    }


def test_policy_raises_memory_candidate_for_safety_event() -> None:
    async def scenario() -> list[dict[str, object]]:
        config = load_config()
        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        actions = ActionManager(session_id="s")
        world = WorldModel(config.world_model)
        policy = PolicyEngine(
            session_id="s", config=config.policy, state=state, actions=actions, world=world
        )
        candidates: list[dict[str, object]] = []

        async def handler(event):
            candidates.append(event.payload)

        bus.subscribe("memory.candidate_raised", handler)
        await actions.start(bus)
        await policy.start(bus)
        await bus.publish(
            make_event(
                "safety.triggered",
                source="test",
                session_id="s",
                payload={"reason": "bumper", "severity": "high"},
                priority=Priority.CRITICAL,
                turn_id="turn-1",
            )
        )
        await bus.drain_once()
        return candidates

    candidates = asyncio.run(scenario())
    assert len(candidates) == 1
    assert candidates[0]["candidate_type"] == "safety_event"
    assert candidates[0]["summary"] == "Safety event: bumper"
    assert candidates[0]["details"] == {"event_type": "safety.triggered", "severity": "high"}
    assert candidates[0]["turn_id"] == "turn-1"


def test_policy_raises_memory_candidate_for_first_named_person_detection() -> None:
    async def scenario() -> list[dict[str, object]]:
        config = load_config()
        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        actions = ActionManager(session_id="s")
        world = WorldModel(config.world_model)
        policy = PolicyEngine(
            session_id="s", config=config.policy, state=state, actions=actions, world=world
        )
        candidates: list[dict[str, object]] = []

        async def handler(event):
            candidates.append(event.payload)

        bus.subscribe("memory.candidate_raised", handler)
        await policy.start(bus)
        for _ in range(2):
            await bus.publish(
                make_event(
                    "vision.person_detected",
                    source="test",
                    session_id="s",
                    payload={"name": "Richer", "embedding_id": "person-1", "confidence": 0.92},
                )
            )
            await bus.drain_once()
        return candidates

    candidates = asyncio.run(scenario())
    assert len(candidates) == 1
    assert candidates[0]["candidate_type"] == "person_seen"
    assert candidates[0]["summary"] == "Person seen: Richer"
    assert candidates[0]["details"] == {
        "person_id": "person-1",
        "name": "Richer",
        "confidence": 0.92,
    }
