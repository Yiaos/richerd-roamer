import asyncio
import json

from roamerd.bridges.cognition.adapters import (
    FallbackCognitionAdapter,
    HttpCognitionAdapter,
    build_cognition_adapter,
)
from roamerd.bridges.cognition.bridge import CognitionBridge, MockCognitionAdapter
from roamerd.bridges.control.bridge import ControlBridge
from roamerd.bridges.control.unix_socket import _command_from_wire
from roamerd.bridges.discord.adapters import HttpDiscordAdapter
from roamerd.bridges.discord.bridge import DiscordBridge
from roamerd.bridges.memory.adapters import HttpMemoryAdapter
from roamerd.bridges.memory.bridge import MemoryBridge
from roamerd.compat.legacy_actions import LEGACY_ACTION_MAP
from roamerd.events import make_event
from roamerd.events.control import ControlCommandPayload, WaitMode
from roamerd.events.memory import MemoryCandidatePayload
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.state_manager import HealthState


class FakeHttpResponse:
    status = 200

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def getcode(self) -> int:
        return self.status

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_cognition_bridge_turns_request_into_response() -> None:
    async def scenario() -> list[str]:
        bus = EventBus(session_id="s")
        bridge = CognitionBridge(session_id="s", adapter=MockCognitionAdapter("ok"))
        seen: list[str] = []

        async def handler(event):
            seen.append(str(event.payload.get("text")))

        bus.subscribe("cognition.response_received", handler)
        await bridge.start(bus)
        await bus.publish(
            make_event(
                "cognition.request_needed",
                source="t",
                session_id="s",
                payload={"text": "复杂", "turn_id": "t", "correlation_id": "c"},
            )
        )
        await bus.drain_once()
        return seen

    assert asyncio.run(scenario()) == ["ok"]


def test_cognition_bridge_opens_and_recovers_circuit_after_consecutive_failures() -> None:
    class FlakyAdapter:
        def __init__(self) -> None:
            self.failures_remaining = 2

        async def request(self, text: str, *, turn_id: str, correlation_id: str):
            if self.failures_remaining:
                self.failures_remaining -= 1
                raise RuntimeError("offline")
            return await MockCognitionAdapter("recovered").request(
                text, turn_id=turn_id, correlation_id=correlation_id
            )

        async def health_check(self) -> HealthState:
            return HealthState.HEALTHY

    async def scenario() -> tuple[list[tuple[str, str]], HealthState, list[str]]:
        bus = EventBus(session_id="s")
        bridge = CognitionBridge(session_id="s", adapter=FlakyAdapter(), failure_threshold=2)
        health_events: list[tuple[str, str]] = []
        responses: list[str] = []

        async def health_handler(event):
            if event.payload.get("name") == "cognition":
                health_events.append(
                    (str(event.payload.get("state")), str(event.payload.get("reason")))
                )

        async def response_handler(event):
            responses.append(str(event.payload.get("text")))

        bus.subscribe("system.health_changed", health_handler)
        bus.subscribe("cognition.response_received", response_handler)
        await bridge.start(bus)
        for index in range(3):
            await bus.publish(
                make_event(
                    "cognition.request_needed",
                    source="test",
                    session_id="s",
                    payload={
                        "text": "复杂",
                        "turn_id": f"turn-{index}",
                        "correlation_id": f"corr-{index}",
                    },
                    correlation_id=f"corr-{index}",
                )
            )
            await bus.drain_once()
        return health_events, await bridge.health_check(), responses

    assert asyncio.run(scenario()) == (
        [("degraded", "RuntimeError"), ("healthy", "None")],
        HealthState.HEALTHY,
        ["recovered"],
    )


def test_http_cognition_adapter_translates_request_and_response() -> None:
    requests: list[dict[str, object]] = []

    def fake_urlopen(request, timeout):
        requests.append(
            {
                "url": request.full_url,
                "method": request.method,
                "body": json.loads(request.data.decode("utf-8")),
                "timeout": timeout,
            }
        )
        return FakeHttpResponse(
            {
                "response_type": "speak_and_action",
                "text": "可以",
                "action_request": {
                    "action_type": "motion.home",
                    "payload": {},
                    "resource": "motion",
                },
                "latency_ms": 12,
            }
        )

    adapter = HttpCognitionAdapter(
        endpoint="http://openclaw.local:3000", timeout_sec=7.0, urlopen=fake_urlopen
    )
    response = asyncio.run(adapter.request("复杂问题", turn_id="turn-1", correlation_id="corr-1"))

    assert requests == [
        {
            "url": "http://openclaw.local:3000/cognition",
            "method": "POST",
            "body": {"text": "复杂问题", "turn_id": "turn-1", "correlation_id": "corr-1"},
            "timeout": 7.0,
        }
    ]
    assert response.text == "可以"
    assert response.action_request is not None
    assert response.action_request.action_type == "motion.home"


def test_fallback_cognition_adapter_uses_secondary_when_primary_fails() -> None:
    class FailingAdapter:
        async def request(self, text: str, *, turn_id: str, correlation_id: str):
            raise RuntimeError("offline")

        async def health_check(self) -> HealthState:
            return HealthState.UNAVAILABLE

    adapter = FallbackCognitionAdapter(
        primary=FailingAdapter(), fallback=MockCognitionAdapter("fallback")
    )
    response = asyncio.run(adapter.request("复杂", turn_id="t", correlation_id="c"))

    assert response.text == "fallback"
    assert asyncio.run(adapter.health_check()) == HealthState.DEGRADED


def test_build_cognition_adapter_uses_configured_openclaw_with_local_fallback() -> None:
    adapter = build_cognition_adapter(
        driver="openclaw",
        endpoint="http://openclaw.local:3000",
        timeout_sec=1.0,
        fallback="local_llm",
        local_endpoint="http://localhost:8080/v1",
    )

    assert isinstance(adapter, FallbackCognitionAdapter)


def test_memory_bridge_buffers_candidate(tmp_path) -> None:
    async def scenario() -> bool:
        bus = EventBus(session_id="s")
        path = tmp_path / "memory.jsonl"
        bridge = MemoryBridge(session_id="s", buffer_path=str(path))
        await bridge.start(bus)
        await bus.publish(
            make_event(
                "memory.candidate_raised",
                source="t",
                session_id="s",
                payload={"candidate_type": "interaction", "summary": "hi"},
            )
        )
        await bus.drain_once()
        return path.exists()

    assert asyncio.run(scenario()) is True


def test_http_memory_adapter_submits_candidate() -> None:
    requests: list[dict[str, object]] = []

    def fake_urlopen(request, timeout):
        requests.append(
            {
                "url": request.full_url,
                "method": request.method,
                "body": json.loads(request.data.decode("utf-8")),
                "timeout": timeout,
            }
        )
        return FakeHttpResponse({"ok": True})

    adapter = HttpMemoryAdapter(
        endpoint="http://memory.local:8200", timeout_sec=2.0, urlopen=fake_urlopen
    )
    ok = asyncio.run(
        adapter.submit_candidate(
            candidate=MemoryCandidatePayload(candidate_type="interaction", summary="hi")
        )
    )

    assert ok is True
    assert requests[0]["url"] == "http://memory.local:8200/memory/candidates"
    assert requests[0]["method"] == "POST"
    assert requests[0]["body"]["candidate_type"] == "interaction"


def test_discord_bridge_sends_cognition_unavailable_notification() -> None:
    class FakeDiscordAdapter:
        def __init__(self) -> None:
            self.messages: list[str] = []

        async def send_message(self, content: str) -> bool:
            self.messages.append(content)
            return True

        async def health_check(self) -> HealthState:
            return HealthState.HEALTHY

    async def scenario() -> list[str]:
        bus = EventBus(session_id="s")
        adapter = FakeDiscordAdapter()
        bridge = DiscordBridge(
            session_id="s",
            enabled=True,
            adapter=adapter,
            mention="@richer",
            reply_instruction="Use roamer voice when replying.",
        )
        await bridge.start(bus)
        await bus.publish(
            make_event(
                "cognition.unavailable",
                source="test",
                session_id="s",
                payload={"reason": "timeout"},
            )
        )
        await bus.drain_once()
        return adapter.messages

    assert asyncio.run(scenario()) == [
        "@richer cognition unavailable: timeout\nUse roamer voice when replying."
    ]


def test_discord_bridge_ingests_json_command_through_policy_path() -> None:
    async def scenario() -> list[dict[str, object]]:
        bus = EventBus(session_id="s")
        bridge = DiscordBridge(session_id="s", enabled=True)
        seen: list[dict[str, object]] = []

        async def handler(event):
            seen.append(event.payload)

        bus.subscribe("control.command_received", handler)
        await bridge.start(bus)
        await bridge.ingest_message(
            message_id="m1",
            author_id="u1",
            content='{"op":"run","action":"speak","args":{"text":"hi"}}',
        )
        await bus.drain_once()
        return seen

    payloads = asyncio.run(scenario())
    assert payloads[0]["source"] == "discord"
    assert payloads[0]["actor"] == "u1"
    assert payloads[0]["action"] == "speak"
    assert payloads[0]["args"] == {"text": "hi"}


def test_http_discord_adapter_posts_message(monkeypatch) -> None:
    requests: list[dict[str, object]] = []
    monkeypatch.setenv("DISCORD_TOKEN_TEST", "token-1")

    def fake_urlopen(request, timeout):
        requests.append(
            {
                "url": request.full_url,
                "method": request.method,
                "body": json.loads(request.data.decode("utf-8")),
                "auth": request.headers.get("Authorization"),
                "timeout": timeout,
            }
        )
        return FakeHttpResponse({"id": "message-1"})

    adapter = HttpDiscordAdapter(
        channel_id="chan-1",
        token_env="DISCORD_TOKEN_TEST",
        timeout_sec=3.0,
        urlopen=fake_urlopen,
    )
    assert asyncio.run(adapter.send_message("hello")) is True
    assert requests == [
        {
            "url": "https://discord.com/api/v10/channels/chan-1/messages",
            "method": "POST",
            "body": {"content": "hello"},
            "auth": "Bot token-1",
            "timeout": 3.0,
        }
    ]


def test_control_bridge_roundtrip() -> None:
    async def scenario() -> bool:
        bus = EventBus(session_id="s")
        bridge = ControlBridge(session_id="s")
        await bridge.start(bus)

        async def responder(event):
            await bus.publish(
                make_event(
                    "control.response_ready",
                    source="test",
                    session_id="s",
                    correlation_id=event.correlation_id,
                    payload={
                        "correlation_id": event.correlation_id,
                        "ok": True,
                        "result": {"pong": True},
                    },
                )
            )

        bus.subscribe("control.command_received", responder)
        bus.start_background()
        response = await bridge.query("ping")
        await bus.stop()
        return bool(response.get("ok"))

    assert asyncio.run(scenario()) is True


def test_control_bridge_publishes_response_sent_after_returning_response() -> None:
    async def scenario() -> list[dict[str, object]]:
        bus = EventBus(session_id="s")
        bridge = ControlBridge(session_id="s")
        sent: list[dict[str, object]] = []
        await bridge.start(bus)

        async def responder(event):
            await bus.publish(
                make_event(
                    "control.response_ready",
                    source="test",
                    session_id="s",
                    correlation_id=event.correlation_id,
                    payload={
                        "correlation_id": event.correlation_id,
                        "request_id": "req-1",
                        "ok": True,
                        "result": {"pong": True},
                    },
                )
            )

        async def sent_handler(event):
            sent.append(event.payload)

        bus.subscribe("control.command_received", responder)
        bus.subscribe("control.response_sent", sent_handler)
        bus.start_background()
        response = await bridge.request(
            ControlCommandPayload(
                op="query",
                target="ping",
                request_id="req-1",
                correlation_id="corr-1",
            )
        )
        await bus.drain_once()
        await bus.stop()
        assert response["ok"] is True
        return sent

    assert asyncio.run(scenario()) == [
        {
            "correlation_id": "corr-1",
            "request_id": "req-1",
            "ok": True,
            "result": {"pong": True},
        }
    ]


def test_control_bridge_completed_wait_returns_terminal_result() -> None:
    async def scenario() -> dict[str, object]:
        bus = EventBus(session_id="s")
        bridge = ControlBridge(session_id="s")
        await bridge.start(bus)

        async def responder(event):
            await bus.publish(
                make_event(
                    "control.response_ready",
                    source="test",
                    session_id="s",
                    correlation_id=event.correlation_id,
                    payload={
                        "correlation_id": event.correlation_id,
                        "ok": True,
                        "result": {"action_id": "act_1", "state": "running"},
                    },
                )
            )
            await bus.publish(
                make_event(
                    "action.completed",
                    source="test",
                    session_id="s",
                    action_id="act_1",
                    payload={"result": {"done": True}},
                )
            )

        bus.subscribe("control.command_received", responder)
        bus.start_background()
        response = await bridge.request(
            ControlCommandPayload(
                op="run",
                action="sense",
                wait=WaitMode.COMPLETED,
                correlation_id="c",
            )
        )
        await bus.stop()
        return response

    assert asyncio.run(scenario())["result"] == {"done": True}


def test_legacy_action_status_wire_maps_to_query() -> None:
    command = _command_from_wire({"command": "action.status", "action_id": "act_1"})
    assert command.op == "query"
    assert command.target == "action.status"
    assert command.args == {"action_id": "act_1"}


def test_legacy_action_map_includes_motion_locate() -> None:
    assert LEGACY_ACTION_MAP["motion.locate"] == "motion.locate"


def test_legacy_socket_timeout_sec_maps_to_timeout_ms() -> None:
    command = _command_from_wire(
        {
            "command": "run",
            "action": "sense",
            "params": {},
            "timeout_sec": 1.5,
            "request_id": "req-1",
        }
    )

    assert command.op == "run"
    assert command.action == "sense"
    assert command.timeout_ms == 1500
    assert command.request_id == "req-1"


def test_control_wire_accepts_trace_id_and_wait_mode_alias() -> None:
    command = _command_from_wire(
        {
            "command": "run",
            "action": "watch",
            "params": {},
            "request_id": "req-1",
            "trace_id": "trace-1",
            "source": "node",
            "actor": "openclaw",
            "authority": "owner",
            "wait_mode": "completed",
            "timeout_ms": 1234,
        }
    )

    assert command.op == "run"
    assert command.action == "watch"
    assert command.request_id == "req-1"
    assert command.trace_id == "trace-1"
    assert command.source == "node"
    assert command.actor == "openclaw"
    assert command.authority == "owner"
    assert command.wait == WaitMode.COMPLETED
    assert command.timeout_ms == 1234


def test_control_bridge_response_preserves_trace_id() -> None:
    async def scenario() -> dict[str, object]:
        bus = EventBus(session_id="s")
        bridge = ControlBridge(session_id="s")
        await bridge.start(bus)

        async def responder(event):
            await bus.publish(
                make_event(
                    "control.response_ready",
                    source="test",
                    session_id="s",
                    correlation_id=event.correlation_id,
                    payload={
                        "correlation_id": event.correlation_id,
                        "ok": True,
                        "result": {"ready": True},
                    },
                )
            )

        bus.subscribe("control.command_received", responder)
        bus.start_background()
        response = await bridge.request(
            ControlCommandPayload(
                op="query",
                target="runtime.status",
                request_id="req-1",
                trace_id="trace-1",
                correlation_id="corr-1",
            )
        )
        await bus.stop()
        return response

    response = asyncio.run(scenario())
    assert response["request_id"] == "req-1"
    assert response["trace_id"] == "trace-1"


def test_legacy_converse_wire_maps_to_completed_listen_action() -> None:
    command = _command_from_wire(
        {
            "command": "converse",
            "args": {"timeout": 2.0, "use_wakeword": False},
            "timeout_sec": 3,
        }
    )

    assert command.op == "run"
    assert command.action == "listen"
    assert command.args == {"timeout": 2.0, "use_wakeword": False}
    assert command.wait == WaitMode.COMPLETED
    assert command.timeout_ms == 3000
