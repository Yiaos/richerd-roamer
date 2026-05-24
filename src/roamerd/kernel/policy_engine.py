from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from roamerd.contracts.errors import ErrorCode
from roamerd.contracts.local_intent import ALLOWED_INTENT_ACTIONS, IntentConfig
from roamerd.events import Event, Priority
from roamerd.kernel.action_manager import (
    ActionManager,
    ActionRequestError,
    PreemptionScope,
)
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.state_manager import HealthState, StateManager
from roamerd.kernel.world_model import WorldModel
from roamerd.types import JSONDict


class PolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActionRequest(PolicyModel):
    action_type: str
    payload: JSONDict = Field(default_factory=dict)
    resource: str = "none"
    priority: Priority = Priority.NORMAL
    source: str
    turn_id: str | None = None


class PolicyDecision(PolicyModel):
    decision_type: Literal["allow", "reject", "preempt", "route_to_cognition", "notify"]
    admitted: bool
    reason: str
    action_id: str | None = None
    preempted: list[str] = Field(default_factory=list)
    error_code: ErrorCode | None = None


class LocalIntentMatch(PolicyModel):
    matched: bool
    intent_name: str | None = None
    action_type: str | None = None
    slots: dict[str, str] = Field(default_factory=dict)
    priority: Priority = Priority.NORMAL
    reason: str = ""


class IntentRule(PolicyModel):
    name: str
    action: str
    patterns: list[str]
    priority: Priority = Priority.NORMAL


class PolicyRuleStore:
    def __init__(self, local_intents: list[IntentRule] | None = None) -> None:
        self.local_intents = local_intents or _default_local_intents()
        self.allowed_actions = ALLOWED_INTENT_ACTIONS

    @classmethod
    def from_config(cls, local_intents: list[IntentConfig]) -> PolicyRuleStore:
        return cls(
            [
                IntentRule(
                    name=intent.name,
                    action=intent.action,
                    patterns=intent.patterns,
                    priority=intent.priority,
                )
                for intent in local_intents
            ]
        )


class IntentMatcher:
    def __init__(self, rules: PolicyRuleStore) -> None:
        self._rules = rules

    def match(self, text: str) -> LocalIntentMatch:
        reminder = _match_reminder(text)
        if reminder is not None:
            return reminder
        goto = _match_goto(text)
        if goto is not None:
            return goto
        for rule in self._rules.local_intents:
            if rule.action not in self._rules.allowed_actions:
                return LocalIntentMatch(
                    matched=False,
                    reason=ErrorCode.CONVERSE_INTENT_INVALID_ACTION.value,
                )
            if any(pattern in text for pattern in rule.patterns):
                return LocalIntentMatch(
                    matched=True,
                    intent_name=rule.name,
                    action_type=rule.action,
                    priority=rule.priority,
                )
        return LocalIntentMatch(matched=False, reason="no_intent_match")


class AdmissionController:
    def __init__(self, rules: PolicyRuleStore, state_manager: StateManager) -> None:
        self._rules = rules
        self._state = state_manager

    def admit(self, request: ActionRequest) -> PolicyDecision:
        if request.action_type not in self._rules.allowed_actions:
            return PolicyDecision(
                decision_type="reject",
                admitted=False,
                reason="unknown action",
                error_code=ErrorCode.CONVERSE_INTENT_INVALID_ACTION,
            )
        module = _module_for_resource(request.resource)
        if module is not None and self._state.get_module_health(module) is HealthState.UNAVAILABLE:
            return PolicyDecision(
                decision_type="reject",
                admitted=False,
                reason=f"{module} module unavailable",
            )
        return PolicyDecision(decision_type="allow", admitted=True, reason="allowed")


class PolicyEngine:
    def __init__(self, *, session_id: str, rules: PolicyRuleStore | None = None) -> None:
        self._session_id = session_id
        self._rules = rules or PolicyRuleStore()
        self._matcher = IntentMatcher(self._rules)
        self._bus: EventBus | None = None
        self._actions: ActionManager | None = None
        self._state: StateManager | None = None
        self._world: WorldModel | None = None
        self._admission: AdmissionController | None = None

    async def start(
        self,
        bus: EventBus,
        action_manager: ActionManager,
        state_manager: StateManager,
        world_model: WorldModel,
    ) -> None:
        self._bus = bus
        self._actions = action_manager
        self._state = state_manager
        self._world = world_model
        self._admission = AdmissionController(self._rules, state_manager)
        bus.subscribe("hearing.transcript_ready", self.handle_event)
        bus.subscribe("hearing.wake_triggered", self.handle_event)
        bus.subscribe("cognition.response_received", self.handle_event)
        bus.subscribe("cognition.unavailable", self.handle_event)
        bus.subscribe("safety.emergency_stop_requested", self.handle_event)
        bus.subscribe("safety.triggered", self.handle_event)
        bus.subscribe("control.command_received", self.handle_event)
        bus.subscribe("memory.policy_update", self.handle_event)

    def match_local_intent(self, text: str) -> LocalIntentMatch:
        return self._matcher.match(text)

    async def handle_event(self, event: Event) -> None:
        if event.event_type == "hearing.transcript_ready":
            await self._handle_transcript(event)
        elif event.event_type == "hearing.wake_triggered":
            await self._handle_wake_triggered(event)
        elif event.event_type == "cognition.response_received":
            await self._handle_cognition_response(event)
        elif event.event_type == "control.command_received":
            await self._handle_control_command(event)
        elif event.event_type == "memory.policy_update":
            self._handle_policy_update(event)
        elif event.event_type in {"safety.emergency_stop_requested", "safety.triggered"}:
            await self._preempt_motion(event, "safety")

    async def admit_action(self, request: ActionRequest) -> PolicyDecision:
        assert self._admission is not None
        decision = self._admission.admit(request)
        if not decision.admitted:
            await self._publish_rejection(request, decision.reason)
            return decision
        assert self._actions is not None
        preempt_decision = await self._maybe_preempt_for_request(request)
        if preempt_decision is not None:
            return preempt_decision
        action = await self._actions.request_action(
            request.action_type,
            request.payload,
            resource=request.resource,
            priority=request.priority,
            turn_id=request.turn_id,
            source_module=_module_for_resource(request.resource),
        )
        if isinstance(action, ActionRequestError):
            return PolicyDecision(
                decision_type="reject",
                admitted=False,
                reason=action.message,
                error_code=action.error_code,
            )
        return decision.model_copy(update={"action_id": action.action_id})

    async def _maybe_preempt_for_request(
        self,
        request: ActionRequest,
    ) -> PolicyDecision | None:
        assert self._actions is not None
        if request.resource == "none":
            return None
        running = self._actions.get_running_actions(request.resource)
        if not running:
            return None
        if not any(request.priority.sort_rank < action.priority.sort_rank for action in running):
            return None
        action = await self._actions.request_action(
            request.action_type,
            request.payload,
            resource=request.resource,
            priority=request.priority,
            turn_id=request.turn_id,
            source_module=_module_for_resource(request.resource),
            preempt_current=True,
        )
        if isinstance(action, ActionRequestError):
            return PolicyDecision(
                decision_type="reject",
                admitted=False,
                reason=action.message,
                error_code=action.error_code,
            )
        return PolicyDecision(
            decision_type="preempt",
            admitted=True,
            reason="preempted lower priority action",
            action_id=action.action_id,
            preempted=[running[0].action_id],
        )

    async def _handle_wake_triggered(self, event: Event) -> None:
        assert self._state is not None
        if self._state.is_speaking:
            await self._publish("policy.wake_ignored", {"reason": "speaking"}, event)
            return
        await self._publish(
            "hearing.listen_requested",
            {"wakeword": str(event.payload.get("wakeword", ""))},
            event,
        )

    async def _handle_transcript(self, event: Event) -> None:
        text = event.payload.get("text")
        if not isinstance(text, str):
            return
        match = self.match_local_intent(text)
        if match.matched and match.action_type is not None:
            await self._handle_local_intent(event, match)
            return
        assert self._state is not None
        if not self._state.cognition_available:
            await self.admit_action(
                ActionRequest(
                    action_type="speech.speak",
                    resource="speaker",
                    payload={"text": "我暂时处理不了复杂请求。"},
                    source="policy_degraded",
                    turn_id=event.turn_id,
                )
            )
            return
        await self._publish(
            "cognition.request_needed",
            {"text": text, "reason": match.reason},
            event,
        )

    async def _handle_local_intent(self, event: Event, match: LocalIntentMatch) -> None:
        assert match.action_type is not None
        await self._publish(
            "policy.local_intent_matched",
            {
                "intent_name": match.intent_name or "",
                "action_type": match.action_type,
                "slots": dict(match.slots),
            },
            event,
        )
        if match.action_type == "emergency_stop":
            await self._preempt_motion(event, "emergency_stop")
            return
        request = self._request_from_match(event, match)
        await self.admit_action(request)

    def _request_from_match(self, event: Event, match: LocalIntentMatch) -> ActionRequest:
        action_type = match.action_type or ""
        resource = _resource_for_action(action_type)
        payload: JSONDict = {}
        if action_type == "motion.goto":
            assert self._world is not None
            location = match.slots.get("location", "")
            place = self._world.resolve_place(location)
            if place is not None:
                payload["target"] = {
                    "name": location,
                    "x": place.center[0],
                    "y": place.center[1],
                    "angle": place.angle,
                }
        elif action_type == "remind.schedule":
            payload.update(match.slots)
        return ActionRequest(
            action_type=action_type,
            payload=payload,
            resource=resource,
            priority=match.priority,
            source="policy_local_intent",
            turn_id=event.turn_id,
        )

    async def _handle_cognition_response(self, event: Event) -> None:
        await self._handle_action_request_event(event)

    async def _handle_control_command(self, event: Event) -> None:
        await self._handle_action_request_event(event)

    async def _handle_action_request_event(self, event: Event) -> None:
        action_request = event.payload.get("action_request")
        if not isinstance(action_request, dict):
            return
        payload = action_request.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}
        request = ActionRequest(
            action_type=str(action_request.get("action_type", "")),
            resource=str(action_request.get("resource", "none")),
            payload=payload,
            source=str(action_request.get("source", "cognition_bridge")),
            turn_id=event.turn_id,
        )
        await self.admit_action(request)

    def _handle_policy_update(self, event: Event) -> None:
        local_intents = event.payload.get("local_intents")
        if not isinstance(local_intents, list):
            return
        intents = [
            IntentConfig.model_validate(intent)
            for intent in local_intents
            if isinstance(intent, dict)
        ]
        self._rules = PolicyRuleStore.from_config(intents)
        self._matcher = IntentMatcher(self._rules)
        if self._state is not None:
            self._admission = AdmissionController(self._rules, self._state)

    async def _preempt_motion(self, event: Event, reason: str) -> None:
        assert self._actions is not None
        await self._actions.preempt(
            PreemptionScope(
                target_resources=["motion"],
                reason=reason,
                source_event=event.event_id,
            )
        )

    async def _publish_rejection(self, request: ActionRequest, reason: str) -> None:
        await self._publish(
            "policy.admission_rejected",
            {"action_type": request.action_type, "reason": reason},
            None,
        )

    async def _publish(
        self,
        event_type: str,
        payload: JSONDict,
        source_event: Event | None,
    ) -> None:
        assert self._bus is not None
        await self._bus.publish(
            Event(
                event_type=event_type,
                source="policy_engine",
                session_id=self._session_id,
                turn_id=source_event.turn_id if source_event else None,
                correlation_id=source_event.correlation_id if source_event else None,
                payload=payload,
            )
        )


def _default_local_intents() -> list[IntentRule]:
    return [
        IntentRule(
            name="emergency_stop",
            action="emergency_stop",
            patterns=["停", "别动", "stop"],
            priority=Priority.CRITICAL,
        ),
        IntentRule(
            name="go_home",
            action="motion.home",
            patterns=["回家", "回充电", "回去充电"],
            priority=Priority.HIGH,
        ),
        IntentRule(name="time_now", action="time.now", patterns=["现在几点", "几点了"]),
        IntentRule(name="sense", action="sense", patterns=["你在哪", "状态"]),
        IntentRule(name="watch", action="watch", patterns=["看一下", "拍张照"]),
        IntentRule(
            name="position",
            action="motion.position",
            patterns=["你在哪个位置", "当前位置"],
        ),
    ]


def _match_goto(text: str) -> LocalIntentMatch | None:
    match = re.fullmatch(r"去(?P<location>.+)", text)
    if match is None:
        return None
    return LocalIntentMatch(
        matched=True,
        intent_name="goto",
        action_type="motion.goto",
        slots={"location": match.group("location")},
        priority=Priority.HIGH,
    )


def _match_reminder(text: str) -> LocalIntentMatch | None:
    match = re.fullmatch(
        r"(?P<num>[0-9一二三四五六七八九十]+)(?P<unit>秒|分钟|小时)后提醒我(?P<text>.*)",
        text,
    )
    if match is None:
        return None
    number = _parse_cn_number(match.group("num"))
    unit = match.group("unit")
    multiplier = {"秒": 1, "分钟": 60, "小时": 3600}[unit]
    reminder_text = match.group("text") or "提醒"
    return LocalIntentMatch(
        matched=True,
        intent_name="reminder",
        action_type="remind.schedule",
        slots={"delay_sec": str(number * multiplier), "text": reminder_text},
    )


def _parse_cn_number(value: str) -> int:
    if value.isdigit():
        return int(value)
    digits = {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if value == "十":
        return 10
    if value.startswith("十"):
        return 10 + digits.get(value[-1], 0)
    if "十" in value:
        left, _, right = value.partition("十")
        return digits.get(left, 0) * 10 + (digits.get(right, 0) if right else 0)
    return digits.get(value, 0)


def _resource_for_action(action_type: str) -> str:
    if action_type.startswith("motion."):
        return "motion"
    if action_type == "speech.speak":
        return "speaker"
    if action_type == "watch":
        return "camera"
    return "none"


def _module_for_resource(resource: str) -> str | None:
    return {
        "motion": "motion",
        "speaker": "speech",
        "camera": "vision",
    }.get(resource)
