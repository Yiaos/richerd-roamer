"""Deterministic policy engine and local intent fast path."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

from roamerd.config.schema import PolicyConfig
from roamerd.contracts.action import ActionRequest, PreemptionScope
from roamerd.contracts.exceptions import ResourceBusyError
from roamerd.contracts.local_intent import LocalIntentMatch, PolicyDecision
from roamerd.events.base import Event, JSONDict, Priority, make_event
from roamerd.events.cognition import CognitionResponsePayload, CognitionResponseType
from roamerd.kernel.action_manager import ActionManager
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.state_manager import HealthState, StateManager
from roamerd.kernel.world_model import WorldModel

_CN_NUMERAL = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_LEADING_JUNK_RE = re.compile(r"^[\s,，。.!！?？:：;；、\"'“”‘’\-_]+")
_SEPARATOR_RE = re.compile(r"[\s\-_]+")


class PolicyEngine:
    def __init__(
        self,
        *,
        session_id: str,
        config: PolicyConfig,
        state: StateManager,
        actions: ActionManager,
        world: WorldModel,
        body_status_snapshot: Callable[[bool], JSONDict] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session_id = session_id
        self._config = config
        self._state = state
        self._actions = actions
        self._world = world
        self._bus: EventBus | None = None
        self._body_status_snapshot = body_status_snapshot
        self._seen_named_people: set[str] = set()
        self._clock = clock
        self._followup_until = 0.0
        self._followup_turns = 0
        self._followup_after_playback = False

    async def start(self, bus: EventBus) -> None:
        self._bus = bus
        for event_type in (
            "hearing.transcript_ready",
            "hearing.wake_triggered",
            "speech.playback_completed",
            "cognition.response_received",
            "cognition.unavailable",
            "safety.emergency_stop_requested",
            "safety.triggered",
            "vision.person_detected",
            "control.command_received",
            "memory.policy_update",
        ):
            bus.subscribe(event_type, self.handle_event)

    async def handle_event(self, event: Event) -> None:
        if event.event_type == "hearing.transcript_ready":
            await self._on_transcript(event)
        elif event.event_type == "hearing.wake_triggered":
            await self._on_wake(event)
        elif event.event_type == "speech.playback_completed":
            await self._on_playback_completed(event)
        elif event.event_type == "cognition.response_received":
            await self._on_cognition_response(event)
        elif event.event_type in {"safety.emergency_stop_requested", "safety.triggered"}:
            await self._on_safety(event)
        elif event.event_type == "vision.person_detected":
            await self._on_person_detected(event)
        elif event.event_type == "control.command_received":
            await self._on_control_command(event)

    async def admit_action(self, request: ActionRequest) -> PolicyDecision:
        if request.action_type not in self._config.allow_actions:
            return await self._reject(request, "action_not_allowed")
        resource = request.resource
        if resource != "none":
            health = self._state.get_module_health(resource)
            if health == HealthState.UNAVAILABLE:
                return await self._reject(request, f"{resource} module unavailable")
        if self._state.get_running_actions if False else False:
            pass
        try:
            action = await self._actions.request_action(
                request.action_type,
                request.payload,
                resource=resource,
                priority=request.priority,
                turn_id=request.turn_id,
            )
        except ResourceBusyError:
            return await self._reject(request, "resource_busy")
        return PolicyDecision(
            decision_type="allow",
            admitted=True,
            reason="allowed",
            action_id=action.action_id,
        )

    def match_local_intent(self, text: str) -> LocalIntentMatch:
        normalized = text.strip()
        if not normalized:
            return LocalIntentMatch(matched=False, reason="empty_text")
        if normalized in self._config.local_voice.stop_phrases or normalized in {
            "停",
            "stop",
            "别动",
        }:
            return LocalIntentMatch(
                matched=True, intent_name="emergency_stop", action_type="emergency_stop"
            )
        slots = _extract_slots(normalized)
        if "delay_sec" in slots:
            return LocalIntentMatch(
                matched=True,
                intent_name="reminder",
                action_type="remind.schedule",
                slots=slots,
            )
        for rule in self._config.local_intents:
            if any(pattern and pattern in normalized for pattern in rule.patterns):
                return LocalIntentMatch(
                    matched=True,
                    intent_name=rule.name,
                    action_type=rule.action,
                    slots=slots,
                )
        if "location" in slots:
            return LocalIntentMatch(
                matched=True,
                intent_name="goto",
                action_type="motion.goto",
                slots=slots,
            )
        return LocalIntentMatch(matched=False, slots=slots, reason="no_intent_match")

    async def _on_transcript(self, event: Event) -> None:
        text = str(event.payload.get("text", ""))
        in_followup = self._followup_remaining() is not None
        if in_followup and self._is_followup_stop_phrase(text):
            self._exit_followup()
            return
        match = self.match_local_intent(text)
        if match.matched and match.action_type is not None:
            if self._bus is not None:
                await self._bus.publish(
                    make_event(
                        "policy.local_intent_matched",
                        source="policy_engine",
                        session_id=self._session_id,
                        payload=match.model_dump(mode="json"),
                        priority=Priority.HIGH,
                        turn_id=event.turn_id,
                    )
                )
            await self._execute_intent(match, event.turn_id)
            if in_followup:
                self._record_followup_turn()
            return
        if len(text.strip()) <= 1:
            if in_followup:
                self._exit_followup()
            return
        await self._route_to_cognition(text, event.turn_id or uuid4().hex[:12])
        if in_followup:
            self._record_followup_turn()

    async def _on_wake(self, event: Event) -> None:
        command_text = event.payload.get("command_text")
        if isinstance(command_text, str) and command_text.strip():
            phrase = event.payload.get("phrase")
            wake_phrases = list(self._config.local_voice.wake_phrases)
            if isinstance(phrase, str):
                wake_phrases.insert(0, phrase)
            stripped_text = _strip_wake_phrase(command_text, wake_phrases)
            match = self.match_local_intent(stripped_text)
            if (
                self._state.is_speaking
                and self._config.local_voice.ignore_wake_while_speaking
                and match.action_type != "emergency_stop"
            ):
                return
            if not stripped_text:
                self._ensure_followup_active()
                await self._request_listen(event)
                return
            await self._on_transcript(
                Event(
                    event_type="hearing.transcript_ready",
                    source="policy_engine",
                    session_id=self._session_id,
                    payload={"text": stripped_text},
                    priority=Priority.HIGH,
                    turn_id=event.turn_id,
                )
            )
            return
        if self._state.is_speaking and self._config.local_voice.ignore_wake_while_speaking:
            return
        await self._request_listen(event)

    async def _request_listen(self, event: Event) -> None:
        payload: JSONDict = {"pre_roll_sec": self._config.local_voice.pre_roll_sec}
        remaining = self._followup_remaining()
        if remaining is not None:
            payload["timeout"] = remaining
        await self.admit_action(
            ActionRequest(
                action_type="listen",
                payload=payload,
                resource="microphone",
                priority=Priority.HIGH,
                source="policy_wake",
                turn_id=event.turn_id or uuid4().hex[:12],
            )
        )

    def _ensure_followup_active(self) -> None:
        if not self._config.local_voice.continuous_followup_enabled:
            return
        if self._followup_remaining() is not None:
            return
        self._followup_until = self._clock() + self._config.local_voice.followup_timeout_sec
        self._followup_turns = 0

    def _followup_remaining(self) -> float | None:
        if not self._config.local_voice.continuous_followup_enabled:
            return None
        remaining = self._followup_until - self._clock()
        if remaining <= 0:
            self._exit_followup()
            return None
        return remaining

    def _exit_followup(self) -> None:
        self._followup_until = 0.0
        self._followup_turns = 0

    def _record_followup_turn(self) -> None:
        self._followup_turns += 1
        if self._followup_turns >= max(1, self._config.local_voice.max_followup_turns):
            self._exit_followup()
            return
        self._followup_until = self._clock() + self._config.local_voice.followup_timeout_sec

    def _is_followup_stop_phrase(self, text: str) -> bool:
        normalized = _normalize_voice_phrase(text)
        return any(
            phrase and _normalize_voice_phrase(phrase) in normalized
            for phrase in self._config.local_voice.stop_phrases
        )

    async def _on_cognition_response(self, event: Event) -> None:
        response = CognitionResponsePayload.model_validate(event.payload)
        if response.response_type in {
            CognitionResponseType.SPEAK,
            CognitionResponseType.SPEAK_AND_ACTION,
        }:
            if response.text:
                decision = await self.admit_action(
                    ActionRequest(
                        action_type="speak",
                        payload={"text": response.text},
                        resource="speaker",
                        priority=Priority.NORMAL,
                        source="cognition_bridge",
                    )
                )
                if decision.admitted:
                    self._followup_after_playback = True
        if response.action_request is not None:
            await self.admit_action(
                ActionRequest(
                    action_type=response.action_request.action_type,
                    payload=response.action_request.payload,
                    resource=response.action_request.resource,
                    priority=Priority.NORMAL,
                    source="cognition_bridge",
                )
            )

    async def _on_playback_completed(self, event: Event) -> None:
        if not self._followup_after_playback:
            return
        self._followup_after_playback = False
        self._ensure_followup_active()

    async def _on_safety(self, event: Event) -> None:
        await self._actions.preempt(
            PreemptionScope(
                target_resources=["motion"],
                reason=str(event.payload.get("reason", "safety")),
                source_event=event.event_id,
            )
        )
        if self._bus is not None:
            await self._bus.publish(
                make_event(
                    "motion.stop_requested",
                    source="policy_engine",
                    session_id=self._session_id,
                    payload={"reason": "safety"},
                    priority=Priority.CRITICAL,
                )
            )
            await self._raise_memory_candidate(
                {
                    "candidate_type": "safety_event",
                    "summary": f"Safety event: {event.payload.get('reason', 'safety')}",
                    "details": {
                        "event_type": event.event_type,
                        "severity": event.payload.get("severity", "unknown"),
                    },
                    "importance": 0.9,
                    "turn_id": event.turn_id,
                },
                turn_id=event.turn_id,
                priority=Priority.HIGH,
            )

    async def _on_person_detected(self, event: Event) -> None:
        name = event.payload.get("name")
        if not isinstance(name, str) or not name.strip():
            return
        person_id = str(event.payload.get("embedding_id") or name)
        if person_id in self._seen_named_people:
            return
        self._seen_named_people.add(person_id)
        await self._raise_memory_candidate(
            {
                "candidate_type": "person_seen",
                "summary": f"Person seen: {name}",
                "details": {
                    "person_id": person_id,
                    "name": name,
                    "confidence": event.payload.get("confidence", 0.0),
                },
                "importance": 0.7,
                "turn_id": event.turn_id,
            },
            turn_id=event.turn_id,
        )

    async def _on_control_command(self, event: Event) -> None:
        op = str(event.payload.get("op", event.payload.get("command", "run")))
        correlation_id = event.correlation_id or str(event.payload.get("correlation_id", ""))
        if op in {"query", "status", "ping", "health", "action.status"}:
            await self._respond(correlation_id, True, self._query_result(event.payload))
            return
        if op == "action.cancel":
            action_id = _action_id_from_control_payload(event.payload)
            if self._actions.get_action(action_id) is None:
                await self._respond(
                    correlation_id,
                    False,
                    {"action_id": action_id, "state": "not_found"},
                    error_code="action.not_found",
                    error_message=f"Unknown action: {action_id}",
                )
                return
            await self._actions.cancel_action(action_id, "client_request")
            await self._respond(
                correlation_id, True, {"action_id": action_id, "state": "cancelled"}
            )
            return
        action_type = str(event.payload.get("action", ""))
        args = event.payload.get("args", event.payload.get("params", {}))
        payload = args if isinstance(args, dict) else {}
        if action_type == "motion.goto":
            resolved = self._resolve_motion_goto_payload(payload)
            if not resolved.get("ok", True):
                await self._respond(
                    correlation_id,
                    False,
                    {"action_id": "", "state": "rejected", "reason": resolved.get("reason", "")},
                    error_code="policy.rejected",
                    error_message=str(resolved.get("reason", "unknown_place")),
                )
                return
            payload = resolved
        resource = _resource_for_action(action_type)
        priority = Priority.HIGH if resource in {"motion", "microphone"} else Priority.NORMAL
        decision = await self.admit_action(
            ActionRequest(
                action_type=action_type,
                payload=payload,
                resource=resource,
                priority=priority,
                source=str(event.payload.get("source", "control")),
            )
        )
        retryable = not decision.admitted and decision.reason == "resource_busy"
        result: JSONDict = {
            "action_id": decision.action_id or "",
            "state": "running" if decision.admitted else "rejected",
        }
        if retryable:
            result["retryable"] = True
        await self._respond(
            correlation_id,
            decision.admitted,
            result,
            error_code=None if decision.admitted else "policy.rejected",
            error_message=None if decision.admitted else decision.reason,
            retryable=retryable,
        )

    async def _execute_intent(self, match: LocalIntentMatch, turn_id: str | None) -> None:
        action_type = match.action_type or ""
        if action_type == "emergency_stop":
            if self._bus is not None:
                await self._bus.publish(
                    make_event(
                        "safety.emergency_stop_requested",
                        source="policy_engine",
                        session_id=self._session_id,
                        payload={"reason": "local_voice"},
                        priority=Priority.CRITICAL,
                        turn_id=turn_id,
                    )
                )
            return
        payload: JSONDict = dict(match.slots)
        if action_type == "motion.goto" and "location" in payload:
            place = self._world.resolve_place(str(payload["location"]))
            if place is None:
                await self._reject(
                    ActionRequest(
                        action_type=action_type,
                        payload=payload,
                        resource="motion",
                        priority=Priority.HIGH,
                        source="local_intent",
                        turn_id=turn_id,
                    ),
                    "unknown_place",
                )
                return
            payload["target"] = place.pose.model_dump(mode="json")
        await self.admit_action(
            ActionRequest(
                action_type=action_type,
                payload=payload,
                resource=_resource_for_action(action_type),
                priority=Priority.HIGH if action_type.startswith("motion.") else Priority.NORMAL,
                source="local_intent",
                turn_id=turn_id,
            )
        )

    def _resolve_motion_goto_payload(self, payload: JSONDict) -> JSONDict:
        if "target" in payload:
            return payload
        location = payload.get("location", payload.get("point"))
        if not isinstance(location, str) or not location.strip():
            return payload
        place = self._world.resolve_place(location)
        if place is None:
            return {"ok": False, "reason": "unknown_place"}
        target = place.pose.model_dump(mode="json")
        angle = payload.get("angle")
        if isinstance(angle, (int, float)):
            target["angle"] = float(angle)
        return {**payload, "target": target}

    async def _route_to_cognition(self, text: str, turn_id: str) -> None:
        if self._bus is None:
            return
        if not self._state.snapshot().cognition_available:
            await self.admit_action(
                ActionRequest(
                    action_type="speak",
                    payload={"text": "我现在处理不了复杂请求，但本地指令仍然可用。"},
                    resource="speaker",
                    priority=Priority.NORMAL,
                    source="policy_reject",
                    turn_id=turn_id,
                )
            )
            return
        correlation_id = uuid4().hex[:12]
        await self._bus.publish(
            make_event(
                "cognition.request_needed",
                source="policy_engine",
                session_id=self._session_id,
                payload={"text": text, "turn_id": turn_id, "correlation_id": correlation_id},
                priority=Priority.NORMAL,
                turn_id=turn_id,
                correlation_id=correlation_id,
            )
        )

    async def _reject(self, request: ActionRequest, reason: str) -> PolicyDecision:
        if self._bus is not None:
            await self._bus.publish(
                make_event(
                    "policy.admission_rejected",
                    source="policy_engine",
                    session_id=self._session_id,
                    payload={"action_type": request.action_type, "reason": reason},
                    priority=Priority.NORMAL,
                    turn_id=request.turn_id,
                )
            )
        return PolicyDecision(decision_type="reject", admitted=False, reason=reason)

    async def _raise_memory_candidate(
        self,
        payload: JSONDict,
        *,
        turn_id: str | None,
        priority: Priority = Priority.NORMAL,
    ) -> None:
        if self._bus is None:
            return
        await self._bus.publish(
            make_event(
                "memory.candidate_raised",
                source="policy_engine",
                session_id=self._session_id,
                payload=payload,
                priority=priority,
                turn_id=turn_id,
            )
        )

    async def _respond(
        self,
        correlation_id: str,
        ok: bool,
        result: JSONDict,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        retryable: bool = False,
    ) -> None:
        if self._bus is None:
            return
        payload: JSONDict = {"correlation_id": correlation_id, "ok": ok, "result": result}
        if error_code is not None:
            payload["error_code"] = error_code
        if error_message is not None:
            payload["error_message"] = error_message
        if retryable:
            payload["retryable"] = True
        await self._bus.publish(
            make_event(
                "control.response_ready",
                source="policy_engine",
                session_id=self._session_id,
                payload=payload,
                correlation_id=correlation_id,
                priority=Priority.HIGH,
            )
        )

    def _query_result(self, payload: JSONDict) -> JSONDict:
        target = (
            "action.status"
            if payload.get("op") == "action.status"
            else str(payload.get("target", payload.get("command", "runtime.status")))
        )
        if target in {"ping", "runtime.status", "status"}:
            state = self._state.snapshot()
            return {
                "session_id": state.session_id,
                "mode": state.mode,
                "started_at": state.started_at.isoformat(),
            }
        if target == "body.status":
            args = payload.get("args")
            full = bool(args.get("full", False)) if isinstance(args, dict) else False
            return self._body_status_result(full)
        if target == "world.snapshot":
            return self._world.snapshot().model_dump(mode="json")
        if target == "world.position":
            position = self._world.get_position()
            return {"position": position.model_dump(mode="json") if position is not None else None}
        if target == "world.people":
            return {
                "people": [
                    person.model_dump(mode="json") for person in self._world.get_people_present()
                ]
            }
        if target == "world.scene":
            scene = self._world.get_scene()
            return {"scene": scene.model_dump(mode="json") if scene is not None else None}
        if target == "actions.list":
            return {
                "actions": [item.model_dump(mode="json") for item in self._actions.list_actions()]
            }
        if target == "action.status":
            args = payload.get("args")
            action_id = str(args.get("action_id", "")) if isinstance(args, dict) else ""
            action = self._actions.get_action(action_id)
            return {"action": action.model_dump(mode="json") if action is not None else None}
        if target == "health":
            state = self._state.snapshot()
            return {
                "modules": {k: v.value for k, v in state.modules.items()},
                "bridges": {k: v.value for k, v in state.bridges.items()},
            }
        return {"target": target, "unsupported": True}

    def _body_status_result(self, full: bool) -> JSONDict:
        body: JSONDict = (
            self._body_status_snapshot(full)
            if self._body_status_snapshot is not None
            else {"available": False}
        )
        state = self._state.snapshot()
        dock_state = "unknown"
        if state.motion.docked is True:
            dock_state = "docked"
        elif state.motion.docked is False:
            dock_state = "undocked"

        network = body.get("network")
        network_status: JSONDict = dict(network) if isinstance(network, dict) else {}
        network_status.setdefault("state", "unknown")

        body["battery"] = {"level": state.motion.battery_percent, "charging": None}
        body["dock"] = {"state": dock_state}
        body["thermal"] = {"pi": body.get("temperature")}
        body["network"] = network_status
        body["ros2"] = {"state": state.modules.get("motion", HealthState.UNAVAILABLE).value}
        body["base"] = {"estop": False, "faults": []}
        body["capabilities"] = {name: health.value for name, health in state.modules.items()}
        return body


def _resource_for_action(action_type: str) -> str:
    if action_type in {"listen", "audio.record"}:
        return "microphone"
    if action_type in {"speak", "audio.play"}:
        return "speaker"
    if action_type in {"watch", "capture"}:
        return "camera"
    if action_type.startswith("motion."):
        return "motion"
    return "none"


def _strip_wake_phrase(text: str, phrases: list[str]) -> str:
    stripped = _LEADING_JUNK_RE.sub("", text).strip()
    candidates = _wake_phrase_candidates(phrases)
    for phrase in candidates:
        if phrase[0].isascii():
            compact_phrase = _canonical_ascii(phrase)
            if _canonical_ascii(stripped).startswith(compact_phrase):
                consumed = _ascii_consumed_length(stripped, compact_phrase)
                return _strip_wake_prefix(stripped, consumed)
            continue
        if stripped.casefold().startswith(phrase.casefold()):
            return _strip_wake_prefix(stripped, len(phrase))
    return stripped


def _normalize_voice_phrase(text: str) -> str:
    return "".join(
        char for char in str(text or "") if char.isalnum() or "\u4e00" <= char <= "\u9fff"
    )


def _wake_phrase_candidates(phrases: list[str]) -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []
    for phrase in phrases:
        stripped = phrase.strip()
        if not stripped:
            continue
        key = stripped.casefold()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(stripped)
    return candidates


def _canonical_ascii(text: str) -> str:
    return _SEPARATOR_RE.sub("", text.casefold())


def _strip_wake_prefix(text: str, length: int) -> str:
    return _LEADING_JUNK_RE.sub("", text[length:]).strip()


def _ascii_consumed_length(text: str, compact_phrase: str) -> int:
    seen = ""
    for index, char in enumerate(text):
        if _SEPARATOR_RE.fullmatch(char):
            continue
        seen += char.casefold()
        if seen == compact_phrase:
            return index + 1
    return 0


def _action_id_from_control_payload(payload: JSONDict) -> str:
    args = payload.get("args")
    if isinstance(args, dict) and args.get("action_id"):
        return str(args["action_id"])
    return str(payload.get("action_id", ""))


def _parse_cn_number(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    if value == "十":
        return 10
    if value.startswith("十") and len(value) == 2:
        ones = _CN_NUMERAL.get(value[1])
        return 10 + ones if ones is not None else None
    if value.endswith("十") and len(value) == 2:
        tens = _CN_NUMERAL.get(value[0])
        return tens * 10 if tens is not None else None
    if "十" in value and len(value) == 3:
        tens = _CN_NUMERAL.get(value[0])
        ones = _CN_NUMERAL.get(value[2])
        if tens is not None and ones is not None:
            return tens * 10 + ones
    return _CN_NUMERAL.get(value)


def _extract_slots(text: str) -> JSONDict:
    slots: JSONDict = {}
    reminder = re.search(
        r"(?P<amount>\d+(?:\.\d+)?|[零一二两三四五六七八九十]{1,3})"
        r"(?P<unit>秒|分钟|分|小时|时|s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hour|hours)"
        r"后(?:提醒我|提醒)?(?P<message>.*)",
        text,
    )
    if reminder:
        amount_raw = reminder.group("amount")
        amount = (
            float(amount_raw)
            if re.fullmatch(r"\d+(?:\.\d+)?", amount_raw)
            else _parse_cn_number(amount_raw)
        )
        unit = reminder.group("unit")
        multiplier = (
            3600
            if unit in {"小时", "时", "h", "hr", "hour", "hours"}
            else 60
            if unit in {"分钟", "分", "m", "min", "mins", "minute", "minutes"}
            else 1
        )
        if amount is not None:
            slots["delay_sec"] = float(amount) * multiplier
            slots["text"] = reminder.group("message").strip(" ，。,.！!") or "提醒"
    goto = re.search(r"去([\u4e00-\u9fa5A-Za-z0-9_-]{1,20})", text)
    if goto:
        slots["location"] = goto.group(1)
    slots["matched_at"] = datetime.now(timezone.utc).isoformat()
    return slots
