import asyncio
import json
import re
from datetime import UTC, datetime

import pytest

from roamerd.events import (
    ActionCancelled,
    ActionCancelRequested,
    ActionCompleted,
    ActionDetached,
    ActionFailed,
    ActionPreempted,
    ActionPreemptRequested,
    ActionStarted,
    AudioLevelChanged,
    CaptureFailed,
    CognitionRequestNeeded,
    CognitionResponseReceived,
    CognitionUnavailable,
    ControlCommandReceived,
    ControlResponseReady,
    ControlResponseSent,
    EmergencyStopRequested,
    Event,
    HandlerTimeout,
    HealthChanged,
    ImageCaptured,
    ListenFailed,
    MemoryCandidateRaised,
    MemoryFlushFailed,
    ModuleReady,
    MotionCompleted,
    MotionFailed,
    MotionPositionUpdated,
    MotionStarted,
    MotionStatusUpdated,
    MotionStopRequested,
    PersonDetected,
    PlaybackCompleted,
    PlaybackFailed,
    PlaybackStarted,
    PolicyUpdate,
    Priority,
    QueueOverflow,
    RecordingStarted,
    SafetyStopApplied,
    SafetyTriggered,
    SceneObserved,
    Shutdown,
    ShutdownRequested,
    SpeechEndpointDetected,
    SpeechStopRequested,
    Startup,
    SynthesisStarted,
    TranscriptReady,
    WakeTriggered,
    WatchdogTriggered,
)
from roamerd.kernel.event_bus import EventBus


def make_event(
    event_type: str,
    *,
    priority: Priority = Priority.NORMAL,
    payload: dict[str, object] | None = None,
) -> Event:
    return Event(
        event_type=event_type,
        source="test",
        session_id="session-1",
        priority=priority,
        payload=payload or {},
    )


class TestEventFoundation:
    def test_event_creation(self) -> None:
        event = Event(
            event_type="hearing.transcript_ready",
            source="hearing_module",
            session_id="session-1",
            turn_id="turn-1",
            payload={"text": "hello", "confidence": 0.91, "tokens": ["hello"]},
        )

        assert event.event_id
        assert event.priority is Priority.NORMAL
        assert event.privacy_level == "normal"
        assert event.retention_hint == "default"

    def test_event_json_roundtrip(self) -> None:
        event = Event(
            event_type="speech.playback_started",
            source="speech_module",
            session_id="session-1",
            action_id="action-1",
            occurred_at=datetime(2026, 5, 23, tzinfo=UTC),
            payload={"path": "/tmp/out.wav", "duration_ms": 1200},
            privacy_level="private",
            retention_hint="short",
        )

        raw = event.model_dump_json()
        decoded = Event.model_validate_json(raw)

        assert json.loads(raw)["event_type"] == "speech.playback_started"
        assert decoded == event

    def test_priority_ordering_is_comparable(self) -> None:
        events = [
            Event(event_type="system.debug", source="test", session_id="s", priority=Priority.LOW),
            Event(
                event_type="safety.triggered",
                source="test",
                session_id="s",
                priority=Priority.CRITICAL,
            ),
            Event(
                event_type="control.command_received",
                source="test",
                session_id="s",
                priority=Priority.HIGH,
            ),
            Event(
                event_type="system.health_changed",
                source="test",
                session_id="s",
                priority=Priority.NORMAL,
            ),
        ]

        assert [event.priority for event in sorted(events)] == [
            Priority.CRITICAL,
            Priority.HIGH,
            Priority.NORMAL,
            Priority.LOW,
        ]

    @pytest.mark.parametrize(
        ("payload_model", "payload"),
        [
            (
                ActionStarted,
                {"action_id": "a1", "action_type": "speech.speak", "resource": "speaker"},
            ),
            (ActionCompleted, {"action_id": "a1", "result": {"ok": True}}),
            (ActionFailed, {"action_id": "a1", "error": {"reason": "failed"}}),
            (ActionCancelled, {"action_id": "a1", "reason": "cancel_timeout"}),
            (ActionPreempted, {"action_id": "a1", "reason": "emergency"}),
            (ActionCancelRequested, {"action_id": "a1", "reason": "user_request"}),
            (ActionPreemptRequested, {"action_id": "a1", "reason": "emergency"}),
            (ActionDetached, {"action_id": "a1", "reason": "client_timeout"}),
            (Startup, {"session_id": "session-1"}),
            (ShutdownRequested, {"reason": "test"}),
            (Shutdown, {"reason": "test"}),
            (ModuleReady, {"module": "hearing"}),
            (HealthChanged, {"component": "hearing", "status": "healthy", "kind": "module"}),
            (
                HandlerTimeout,
                {"event_type": "hearing.transcript_ready", "handler": "sub-1", "timeout_sec": 1.0},
            ),
            (
                QueueOverflow,
                {"priority": "low", "dropped_event_type": "system.health_changed"},
            ),
            (WatchdogTriggered, {"stalled_for_sec": 1.5}),
            (WakeTriggered, {"wakeword": "su03t", "confidence": 1.0, "follow_up": False}),
            (RecordingStarted, {"device": "mock", "sample_rate": 16000, "channels": 1}),
            (
                SpeechEndpointDetected,
                {"audio_path": None, "duration_ms": 0, "speech_ms": 0},
            ),
            (
                TranscriptReady,
                {
                    "text": "去客厅",
                    "confidence": 0.8,
                    "follow_up_eligible": True,
                    "fallback_eligible": True,
                },
            ),
            (AudioLevelChanged, {"rms": 0.42, "peak": 0.8}),
            (ListenFailed, {"error_code": "NO_SPEECH", "message": "no speech detected"}),
            (SynthesisStarted, {"text_len": 2, "driver": "FakeTtsDriver"}),
            (PlaybackStarted, {"path": "/tmp/speak.wav", "duration_ms": 100}),
            (PlaybackCompleted, {"path": "/tmp/speak.wav", "elapsed_ms": 100}),
            (PlaybackFailed, {"error_code": "PLAYBACK_FAILED", "message": "speaker down"}),
            (SpeechStopRequested, {"reason": "cancel"}),
            (ImageCaptured, {"path": "/tmp/image.jpg", "width": 640, "height": 480}),
            (
                SceneObserved,
                {
                    "description": "room",
                    "objects": [{"label": "cup", "confidence": 0.9}],
                },
            ),
            (
                PersonDetected,
                {
                    "person_id": "p1",
                    "name": "Alice",
                    "confidence": 0.9,
                    "position_hint": "desk",
                    "source": "vision",
                },
            ),
            (CaptureFailed, {"error_code": "CAPTURE_FAILED", "message": "camera down"}),
            (MotionStopRequested, {"reason": "safety.triggered"}),
            (MotionStarted, {"action_id": "a1", "action_type": "motion.goto"}),
            (
                MotionCompleted,
                {"action_id": "a1", "status": "arrived", "x": 1.0, "y": 2.0, "angle": None},
            ),
            (MotionFailed, {"action_id": "a1", "message": "nav failed"}),
            (MotionPositionUpdated, {"x": 1.0, "y": 2.0, "angle": None}),
            (MotionStatusUpdated, {"status": "moving", "battery_percent": 80.0}),
            (EmergencyStopRequested, {"reason": "bumper"}),
            (SafetyTriggered, {"reason": "bumper", "severity": "critical"}),
            (SafetyStopApplied, {"reason": "bumper", "stopped_resources": ["motion"]}),
            (CognitionRequestNeeded, {"text": "hello", "reason": "no_intent_match"}),
            (
                CognitionResponseReceived,
                {
                    "response_type": "speech",
                    "text": "hello",
                    "correlation_id": "corr-1",
                },
            ),
            (CognitionUnavailable, {"reason": "timeout", "correlation_id": "corr-1"}),
            (MemoryCandidateRaised, {"kind": "interaction", "content": {"text": "hello"}}),
            (MemoryFlushFailed, {"reason": "down", "buffer_size": 3, "failure_count": 1}),
            (PolicyUpdate, {"policy_id": "quiet-hours", "enabled": True}),
            (
                ControlCommandReceived,
                {"request_id": "req-1", "op": "ping", "args": {"verbose": True}},
            ),
            (ControlResponseReady, {"request_id": "req-1", "status": "ok"}),
            (ControlResponseSent, {"request_id": "req-1", "bytes_sent": 42}),
        ],
    )
    def test_typed_event_payloads_expose_canonical_event_type(
        self,
        payload_model: type,
        payload: dict[str, object],
    ) -> None:
        instance = payload_model.model_validate(payload)
        event = Event.from_payload(
            instance,
            source="test",
            session_id="session-1",
        )

        assert re.fullmatch(r"[a-z]+\.[a-z0-9_]+", event.event_type)
        assert event.event_type == payload_model.EVENT_TYPE
        assert event.payload == instance.model_dump()

    def test_pascal_case_event_types_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="dotted lowercase"):
            Event(event_type="WakeTriggered", source="test", session_id="session-1")


class TestEventBus:
    @pytest.mark.asyncio
    async def test_priority_ordering_dispatches_critical_before_low(self) -> None:
        bus = EventBus()
        seen: list[str] = []

        async def handler(event: Event) -> None:
            seen.append(event.event_type)

        bus.subscribe_pattern("*", handler)
        await bus.publish(make_event("system.health_changed", priority=Priority.LOW))
        await bus.publish(make_event("safety.triggered", priority=Priority.CRITICAL))
        await bus.run_until_idle()

        assert seen == ["safety.triggered", "system.health_changed"]

    @pytest.mark.asyncio
    async def test_same_priority_keeps_fifo_order(self) -> None:
        bus = EventBus()
        seen: list[int] = []

        async def handler(event: Event) -> None:
            seen.append(int(event.payload["index"]))

        bus.subscribe("hearing.transcript_ready", handler)
        await bus.publish(make_event("hearing.transcript_ready", payload={"index": 1}))
        await bus.publish(make_event("hearing.transcript_ready", payload={"index": 2}))
        await bus.run_until_idle()

        assert seen == [1, 2]

    @pytest.mark.asyncio
    async def test_subscribe_pattern_and_unsubscribe(self) -> None:
        bus = EventBus()
        seen: list[str] = []

        async def handler(event: Event) -> None:
            seen.append(event.event_type)

        subscription = bus.subscribe_pattern("hearing.*", handler)
        await bus.publish(make_event("hearing.wake_triggered"))
        await bus.publish(make_event("speech.playback_started"))
        await bus.run_until_idle()
        bus.unsubscribe(subscription.id)
        await bus.publish(make_event("hearing.transcript_ready"))
        await bus.run_until_idle()

        assert seen == ["hearing.wake_triggered"]

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_stop_dispatch(self) -> None:
        bus = EventBus()
        seen: list[str] = []

        async def broken(_: Event) -> None:
            raise RuntimeError("boom")

        async def healthy(event: Event) -> None:
            seen.append(event.event_type)

        bus.subscribe("system.health_changed", broken)
        bus.subscribe("system.health_changed", healthy)
        await bus.publish(make_event("system.health_changed"))
        await bus.run_until_idle()

        assert seen == ["system.health_changed"]

    @pytest.mark.asyncio
    async def test_low_queue_overflow_drops_oldest_and_emits_event(self) -> None:
        bus = EventBus(low_maxsize=1)
        seen: list[str] = []

        async def handler(event: Event) -> None:
            seen.append(event.event_type)

        bus.subscribe_pattern("*", handler)
        await bus.publish(make_event("system.health_changed", priority=Priority.LOW))
        await bus.publish(make_event("system.module_ready", priority=Priority.LOW))
        await bus.run_until_idle()

        assert seen == ["system.queue_overflow", "system.module_ready"]

    @pytest.mark.asyncio
    async def test_stop_drains_queued_events(self) -> None:
        bus = EventBus()
        seen: list[str] = []

        async def handler(event: Event) -> None:
            seen.append(event.event_type)

        bus.subscribe_pattern("*", handler)
        await bus.publish(make_event("system.startup"))
        await bus.stop()

        assert seen == ["system.startup"]

    def test_handler_must_be_async(self) -> None:
        bus = EventBus()

        def handler(_: Event) -> None:
            return None

        with pytest.raises(TypeError, match="async"):
            bus.subscribe("system.startup", handler)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_run_dispatches_until_stop(self) -> None:
        bus = EventBus()
        seen = asyncio.Event()

        async def handler(_: Event) -> None:
            seen.set()

        bus.subscribe("system.startup", handler)
        runner = asyncio.create_task(bus.run())
        await bus.publish(make_event("system.startup"))
        await asyncio.wait_for(seen.wait(), timeout=0.5)
        await bus.stop()
        await asyncio.wait_for(runner, timeout=0.5)

    @pytest.mark.asyncio
    async def test_handler_timeout_cancels_handler_and_emits_event(self) -> None:
        bus = EventBus(handler_timeout_sec=0.01)
        cancelled = asyncio.Event()
        timeout_events: list[Event] = []

        async def slow(_: Event) -> None:
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        async def timeout_handler(event: Event) -> None:
            timeout_events.append(event)

        bus.subscribe("hearing.transcript_ready", slow)
        bus.subscribe("system.handler_timeout", timeout_handler)
        await bus.publish(make_event("hearing.transcript_ready"))
        await bus.run_until_idle()

        assert cancelled.is_set()
        assert [event.event_type for event in timeout_events] == ["system.handler_timeout"]
        assert timeout_events[0].payload["event_type"] == "hearing.transcript_ready"

    @pytest.mark.asyncio
    async def test_high_queue_backpressures_without_dropping_events(self) -> None:
        bus = EventBus(high_maxsize=1)
        seen: list[int] = []

        async def handler(event: Event) -> None:
            seen.append(int(event.payload["index"]))

        bus.subscribe("control.command_received", handler)
        await bus.publish(
            make_event(
                "control.command_received",
                priority=Priority.HIGH,
                payload={"index": 1},
            )
        )
        second_publish = asyncio.create_task(
            bus.publish(
                make_event(
                    "control.command_received",
                    priority=Priority.HIGH,
                    payload={"index": 2},
                )
            )
        )
        await asyncio.sleep(0)

        assert not second_publish.done()

        await bus.run_until_idle()
        await asyncio.wait_for(second_publish, timeout=0.5)
        await bus.run_until_idle()

        assert seen == [1, 2]

    @pytest.mark.asyncio
    async def test_critical_fast_path_cancels_and_requeues_slow_normal_handler(self) -> None:
        bus = EventBus(handler_timeout_sec=1.0, critical_fast_path_after_sec=0.01)
        normal_started = asyncio.Event()
        normal_cancelled = asyncio.Event()
        seen: list[str] = []
        normal_attempts = 0

        async def normal_handler(event: Event) -> None:
            nonlocal normal_attempts
            normal_attempts += 1
            if normal_attempts == 1:
                normal_started.set()
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    normal_cancelled.set()
                    raise
            seen.append(event.event_type)

        async def critical_handler(event: Event) -> None:
            seen.append(event.event_type)

        bus.subscribe("system.health_changed", normal_handler)
        bus.subscribe("safety.triggered", critical_handler)
        runner = asyncio.create_task(bus.run())
        await bus.publish(make_event("system.health_changed"))
        await asyncio.wait_for(normal_started.wait(), timeout=0.5)
        await asyncio.sleep(0.02)
        await bus.publish(make_event("safety.triggered", priority=Priority.CRITICAL))

        while len(seen) < 2:
            await asyncio.sleep(0.01)

        await bus.stop()
        await asyncio.wait_for(runner, timeout=0.5)

        assert normal_cancelled.is_set()
        assert seen == ["safety.triggered", "system.health_changed"]

    @pytest.mark.asyncio
    async def test_safety_watchdog_emits_stall_event(self) -> None:
        bus = EventBus(
            handler_timeout_sec=0.06,
            watchdog_interval_sec=0.01,
            watchdog_stall_after_sec=0.02,
        )
        watchdog_events: list[Event] = []

        async def slow(_: Event) -> None:
            await asyncio.sleep(1)

        async def watchdog_handler(event: Event) -> None:
            watchdog_events.append(event)

        bus.subscribe("system.health_changed", slow)
        bus.subscribe("system.watchdog_triggered", watchdog_handler)
        runner = asyncio.create_task(bus.run())
        await bus.publish(make_event("system.health_changed"))

        while not watchdog_events:
            await asyncio.sleep(0.01)

        await bus.stop()
        await asyncio.wait_for(runner, timeout=0.5)

        assert watchdog_events[0].payload["stalled_for_sec"] >= 0.02
