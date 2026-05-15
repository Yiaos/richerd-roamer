import asyncio
from pathlib import Path

from roamerd.capabilities.hearing.drivers.mock import MockSttDriver
from roamerd.capabilities.hearing.module import HearingModule
from roamerd.capabilities.motion.drivers.mock import MockRos2NavDriver
from roamerd.capabilities.motion.module import MotionModule
from roamerd.capabilities.reminder import ReminderModule
from roamerd.capabilities.speech.drivers.mock import MockPlaybackDriver, MockTtsDriver
from roamerd.capabilities.speech.module import SpeechModule
from roamerd.capabilities.vision.drivers.mock import MockCameraDriver
from roamerd.capabilities.vision.module import VisionModule
from roamerd.events.base import Event, make_event
from roamerd.events.hearing import WakePayload
from roamerd.events.motion import MotionTarget, Position
from roamerd.kernel.action_manager import ActionManager
from roamerd.kernel.event_bus import EventBus


def test_hearing_speech_vision_motion_modules_complete_actions(tmp_path) -> None:
    async def scenario() -> dict[str, str]:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        await actions.start(bus)
        hearing = HearingModule(
            session_id="s", action_manager=actions, stt_driver=MockSttDriver(["回充电"])
        )
        speech = SpeechModule(
            session_id="s",
            action_manager=actions,
            tts_driver=MockTtsDriver(),
            playback_driver=MockPlaybackDriver(),
        )
        vision = VisionModule(
            session_id="s", action_manager=actions, camera_driver=MockCameraDriver()
        )
        motion = MotionModule(session_id="s", action_manager=actions, driver=MockRos2NavDriver())
        for module in (hearing, speech, vision, motion):
            await module.start(bus)
        listen = await actions.request_action("listen", {}, resource="microphone")
        speak = await actions.request_action(
            "speak", {"text": "hi", "save_path": str(tmp_path / "x.wav")}, resource="speaker"
        )
        watch = await actions.request_action(
            "watch", {"output": str(tmp_path / "x.jpg")}, resource="camera"
        )
        move = await actions.request_action(
            "motion.goto", {"target": {"x": 1, "y": 2}}, resource="motion"
        )
        await bus.drain_once()
        locate = await actions.request_action("motion.locate", {}, resource="motion")
        await bus.drain_once()
        return {
            "listen": actions.get_action(listen.action_id).status.value,  # type: ignore[union-attr]
            "speak": actions.get_action(speak.action_id).status.value,  # type: ignore[union-attr]
            "watch": actions.get_action(watch.action_id).status.value,  # type: ignore[union-attr]
            "move": actions.get_action(move.action_id).status.value,  # type: ignore[union-attr]
            "locate": actions.get_action(locate.action_id).status.value,  # type: ignore[union-attr]
        }

    assert asyncio.run(scenario()) == {
        "listen": "completed",
        "speak": "completed",
        "watch": "completed",
        "move": "completed",
        "locate": "completed",
    }


def test_vision_module_publishes_person_detections_from_capture_result() -> None:
    class DetectingCameraDriver(MockCameraDriver):
        async def capture(
            self,
            *,
            output: str | None = None,
            width: int | None = None,
            height: int | None = None,
        ) -> dict[str, object]:
            result = await super().capture(output=output, width=width, height=height)
            return {
                **result,
                "people": [
                    {
                        "name": "Richer",
                        "embedding_id": "person-1",
                        "confidence": 0.92,
                        "bbox": [1, 2, 3, 4],
                    }
                ],
            }

    async def scenario() -> list[dict[str, object]]:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        await actions.start(bus)
        module = VisionModule(
            session_id="s", action_manager=actions, camera_driver=DetectingCameraDriver()
        )
        seen: list[dict[str, object]] = []

        async def handler(event: Event) -> None:
            seen.append(event.payload)

        bus.subscribe("vision.person_detected", handler)
        await module.start(bus)
        await actions.request_action("capture", {}, resource="camera")
        await bus.drain_once()
        await asyncio.sleep(0.01)
        return seen

    assert asyncio.run(scenario()) == [
        {
            "name": "Richer",
            "embedding_id": "person-1",
            "confidence": 0.92,
            "bbox": [1, 2, 3, 4],
        }
    ]


def test_vision_module_publishes_scene_observed_from_capture_objects() -> None:
    class ObjectDetectingCameraDriver(MockCameraDriver):
        async def capture(
            self,
            *,
            output: str | None = None,
            width: int | None = None,
            height: int | None = None,
        ) -> dict[str, object]:
            result = await super().capture(output=output, width=width, height=height)
            return {**result, "objects": ["cup", "chair"], "model": "local-yolo"}

    async def scenario() -> list[dict[str, object]]:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        await actions.start(bus)
        module = VisionModule(
            session_id="s", action_manager=actions, camera_driver=ObjectDetectingCameraDriver()
        )
        seen: list[dict[str, object]] = []

        async def handler(event: Event) -> None:
            seen.append(event.payload)

        bus.subscribe("vision.scene_observed", handler)
        await module.start(bus)
        await actions.request_action("capture", {}, resource="camera")
        await bus.drain_once()
        await asyncio.sleep(0.01)
        return seen

    assert asyncio.run(scenario()) == [
        {
            "description": None,
            "objects": ["cup", "chair"],
            "image_path": "/tmp/roamerd-image.jpg",
            "model": "local-yolo",
        }
    ]


def test_motion_module_waits_until_goto_target_reached() -> None:
    class DelayedDriver:
        def __init__(self) -> None:
            self.checks = 0

        async def move_to(self, target: MotionTarget) -> dict[str, object]:
            return {"ok": True}

        async def stop(self) -> None:
            return None

        async def dock(self) -> dict[str, object]:
            return {"ok": True}

        async def get_position(self) -> Position:
            self.checks += 1
            if self.checks == 1:
                return Position(x=0, y=0)
            return Position(x=10, y=0)

        async def get_status(self) -> dict[str, object]:
            return {"ok": True, "docked": False}

        async def health_check(self):
            from roamerd.kernel.state_manager import HealthState

            return HealthState.HEALTHY

    async def scenario() -> tuple[str, dict[str, object], int]:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        driver = DelayedDriver()
        module = MotionModule(
            session_id="s",
            action_manager=actions,
            driver=driver,
            wait_timeout_sec=0.5,
            poll_interval_sec=0.0,
            arrival_tolerance=0.1,
        )
        await actions.start(bus)
        await module.start(bus)
        action = await actions.request_action(
            "motion.goto",
            {"target": {"x": 10, "y": 0}, "wait": True},
            resource="motion",
        )
        await bus.drain_once()
        completed = actions.get_action(action.action_id)
        assert completed is not None
        return completed.status.value, completed.result or {}, driver.checks

    status, result, checks = asyncio.run(scenario())
    assert status == "completed"
    assert result["final_position"] == {
        "x": 10.0,
        "y": 0.0,
        "angle": None,
        "frame": "valetudo_pixel",
    }
    assert checks == 2


def test_motion_module_rejects_goto_when_target_frame_differs_from_robot_frame() -> None:
    class FrameCheckingDriver:
        def __init__(self) -> None:
            self.moves: list[MotionTarget] = []

        async def move_to(self, target: MotionTarget) -> dict[str, object]:
            self.moves.append(target)
            return {"ok": True}

        async def stop(self) -> None:
            return None

        async def dock(self) -> dict[str, object]:
            return {"ok": True}

        async def get_position(self) -> Position:
            return Position(x=0, y=0, frame="map")

        async def get_status(self) -> dict[str, object]:
            return {"ok": True, "docked": False}

        async def health_check(self):
            from roamerd.kernel.state_manager import HealthState

            return HealthState.HEALTHY

    async def scenario() -> tuple[str, dict[str, object], int]:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        driver = FrameCheckingDriver()
        module = MotionModule(session_id="s", action_manager=actions, driver=driver)
        await actions.start(bus)
        await module.start(bus)
        action = await actions.request_action(
            "motion.goto",
            {"target": {"x": 10, "y": 0, "frame": "valetudo_pixel"}, "wait": False},
            resource="motion",
        )
        await bus.drain_once()
        failed = actions.get_action(action.action_id)
        assert failed is not None
        return failed.status.value, failed.error or {}, len(driver.moves)

    assert asyncio.run(scenario()) == (
        "failed",
        {
            "error_code": "motion.frame_mismatch",
            "error_message": "target frame valetudo_pixel does not match robot frame map",
        },
        0,
    )


def test_motion_status_action_publishes_status_updated() -> None:
    async def scenario() -> list[dict[str, object]]:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        await actions.start(bus)
        driver = MockRos2NavDriver()
        module = MotionModule(session_id="s", action_manager=actions, driver=driver)
        seen: list[dict[str, object]] = []

        async def handler(event: Event) -> None:
            seen.append(event.payload)

        bus.subscribe("motion.status_updated", handler)
        await module.start(bus)
        await actions.request_action("motion.status", {}, resource="motion")
        await bus.drain_once()
        await asyncio.sleep(0.01)
        return seen

    assert asyncio.run(scenario()) == [{"battery_percent": 100, "docked": False, "state": "idle"}]


def test_motion_module_stops_driver_on_action_cancelled_or_preempted() -> None:
    async def scenario() -> list[bool]:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        driver = MockRos2NavDriver()
        module = MotionModule(session_id="s", action_manager=actions, driver=driver)
        await module.start(bus)
        await bus.publish(
            make_event(
                "action.cancelled",
                source="test",
                session_id="s",
                action_id="act_cancel",
                payload={"action_type": "motion.goto"},
            )
        )
        await bus.drain_once()
        cancelled_stopped = driver.stopped
        driver.stopped = False
        await bus.publish(
            make_event(
                "action.preempted",
                source="test",
                session_id="s",
                action_id="act_preempt",
                payload={"action_type": "motion.goto"},
            )
        )
        await bus.drain_once()
        return [cancelled_stopped, driver.stopped]

    assert asyncio.run(scenario()) == [True, True]


def test_motion_module_stops_driver_and_publishes_stop_applied_on_safety_triggered() -> None:
    async def scenario() -> tuple[bool, list[dict[str, object]]]:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        driver = MockRos2NavDriver()
        module = MotionModule(session_id="s", action_manager=actions, driver=driver)
        stop_applied: list[dict[str, object]] = []

        async def handler(event: Event) -> None:
            stop_applied.append(event.payload)

        bus.subscribe("safety.stop_applied", handler)
        await module.start(bus)
        await bus.publish(
            make_event(
                "safety.triggered",
                source="test",
                session_id="s",
                payload={"reason": "bumper", "severity": "high"},
            )
        )
        await bus.drain_once()
        return driver.stopped, stop_applied

    assert asyncio.run(scenario()) == (
        True,
        [{"reason": "bumper", "source_event": "safety.triggered"}],
    )


def test_motion_cancelled_goto_stops_and_cancels_active_driver_call() -> None:
    class BlockingMotionDriver(MockRos2NavDriver):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.cancelled = False

        async def move_to(self, target: MotionTarget) -> dict[str, object]:
            self.started.set()
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            return await super().move_to(target)

    async def scenario() -> tuple[bool, bool, str]:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        await actions.start(bus)
        driver = BlockingMotionDriver()
        module = MotionModule(session_id="s", action_manager=actions, driver=driver)
        await module.start(bus)
        bus.start_background()
        action = await actions.request_action(
            "motion.goto",
            {"target": {"x": 1, "y": 2}, "wait": False},
            resource="motion",
        )
        await asyncio.wait_for(driver.started.wait(), timeout=0.5)
        await actions.cancel_action(action.action_id, "client_request")
        await asyncio.sleep(0.05)
        status = actions.get_action(action.action_id)
        assert status is not None
        stopped_before_cleanup = driver.stopped
        driver.release.set()
        await module.stop()
        await bus.stop()
        return stopped_before_cleanup, driver.cancelled, status.status.value

    assert asyncio.run(scenario()) == (True, True, "cancelled")


def test_speech_module_stops_playback_on_action_cancelled_or_preempted() -> None:
    async def scenario() -> list[bool]:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        playback = MockPlaybackDriver()
        module = SpeechModule(
            session_id="s",
            action_manager=actions,
            tts_driver=MockTtsDriver(),
            playback_driver=playback,
        )
        await module.start(bus)
        await bus.publish(
            make_event(
                "action.cancelled",
                source="test",
                session_id="s",
                action_id="act_cancel",
                payload={"action_type": "speak"},
            )
        )
        await bus.drain_once()
        cancelled_stopped = playback.stopped
        playback.stopped = False
        await bus.publish(
            make_event(
                "action.preempted",
                source="test",
                session_id="s",
                action_id="act_preempt",
                payload={"action_type": "speak"},
            )
        )
        await bus.drain_once()
        return [cancelled_stopped, playback.stopped]

    assert asyncio.run(scenario()) == [True, True]


def test_capability_modules_stop_io_on_shutdown_requested() -> None:
    class ShutdownWakeDriver:
        def __init__(self) -> None:
            self.stopped = False

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            self.stopped = True

        async def wait_for_wake(self) -> WakePayload | None:
            await asyncio.Event().wait()
            return None

        async def health_check(self):
            from roamerd.kernel.state_manager import HealthState

            return HealthState.HEALTHY

    async def scenario() -> tuple[bool, bool, bool]:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        wake_driver = ShutdownWakeDriver()
        hearing = HearingModule(
            session_id="s",
            action_manager=actions,
            stt_driver=MockSttDriver(),
            wake_driver=wake_driver,
        )
        playback = MockPlaybackDriver()
        speech = SpeechModule(
            session_id="s",
            action_manager=actions,
            tts_driver=MockTtsDriver(),
            playback_driver=playback,
        )
        motion_driver = MockRos2NavDriver()
        motion = MotionModule(session_id="s", action_manager=actions, driver=motion_driver)
        for module in (hearing, speech, motion):
            await module.start(bus)
        await bus.publish(make_event("system.shutdown_requested", source="test", session_id="s"))
        await bus.drain_once()
        return wake_driver.stopped, playback.stopped, motion_driver.stopped

    assert asyncio.run(scenario()) == (True, True, True)


def test_speech_stop_requested_reaches_driver_during_active_playback() -> None:
    class BlockingPlaybackDriver(MockPlaybackDriver):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def play(self, audio_path: str, *, device: str = "default") -> dict[str, object]:
            self.started.set()
            await self.release.wait()
            return await super().play(audio_path, device=device)

    async def scenario() -> bool:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        await actions.start(bus)
        playback = BlockingPlaybackDriver()
        module = SpeechModule(
            session_id="s",
            action_manager=actions,
            tts_driver=MockTtsDriver(),
            playback_driver=playback,
        )
        await module.start(bus)
        bus.start_background()
        await actions.request_action(
            "speak", {"text": "hi", "save_path": "/tmp/roamerd-stop-test.wav"}, resource="speaker"
        )
        await asyncio.wait_for(playback.started.wait(), timeout=0.5)
        await bus.publish(make_event("speech.stop_requested", source="test", session_id="s"))
        await asyncio.sleep(0.05)
        stopped_before_playback_finished = playback.stopped
        playback.release.set()
        await asyncio.sleep(0.05)
        await bus.stop()
        return stopped_before_playback_finished

    assert asyncio.run(scenario()) is True


def test_speech_stop_requested_cancels_active_synthesis_and_publishes_stopped() -> None:
    class BlockingTtsDriver(MockTtsDriver):
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.cancelled = False

        async def synthesize(
            self, text: str, output_path: str, *, style: str | None = None
        ) -> dict[str, object]:
            self.started.set()
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            return await super().synthesize(text, output_path, style=style)

    async def scenario() -> tuple[bool, bool, list[dict[str, object]], str, str]:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        await actions.start(bus)
        tts = BlockingTtsDriver()
        playback = MockPlaybackDriver()
        module = SpeechModule(
            session_id="s",
            action_manager=actions,
            tts_driver=tts,
            playback_driver=playback,
        )
        stopped_events: list[dict[str, object]] = []

        async def handler(event: Event) -> None:
            stopped_events.append(event.payload)

        bus.subscribe("speech.stopped", handler)
        await module.start(bus)
        bus.start_background()
        action = await actions.request_action(
            "speak",
            {"text": "hi", "save_path": "/tmp/roamerd-stop-synthesis.wav"},
            resource="speaker",
        )
        await asyncio.wait_for(tts.started.wait(), timeout=0.5)
        await bus.publish(make_event("speech.stop_requested", source="test", session_id="s"))
        await asyncio.sleep(0.05)
        status = actions.get_action(action.action_id)
        assert status is not None
        tts.release.set()
        await module.stop()
        await bus.stop()
        return (
            tts.cancelled,
            playback.stopped,
            stopped_events,
            status.status.value,
            action.action_id,
        )

    cancelled, playback_stopped, stopped_events, status, action_id = asyncio.run(scenario())
    assert cancelled is True
    assert playback_stopped is True
    assert stopped_events == [{"action_id": action_id, "reason": "stop_requested"}]
    assert status == "completed"


def test_hearing_cancelled_listen_cancels_active_transcription() -> None:
    class BlockingSttDriver(MockSttDriver):
        def __init__(self) -> None:
            super().__init__(["ignored"])
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.cancelled = False

        async def transcribe(self, audio_path=None, *, timeout: float = 10.0):
            self.started.set()
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            return await super().transcribe(audio_path, timeout=timeout)

    async def scenario() -> tuple[bool, str]:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        await actions.start(bus)
        driver = BlockingSttDriver()
        module = HearingModule(session_id="s", action_manager=actions, stt_driver=driver)
        await module.start(bus)
        bus.start_background()
        action = await actions.request_action("listen", {"timeout": 30}, resource="microphone")
        await asyncio.wait_for(driver.started.wait(), timeout=0.5)
        await actions.cancel_action(action.action_id, "client_request")
        await asyncio.sleep(0.05)
        status = actions.get_action(action.action_id)
        assert status is not None
        driver.release.set()
        await module.stop()
        await bus.stop()
        return driver.cancelled, status.status.value

    assert asyncio.run(scenario()) == (True, "cancelled")


def test_hearing_listen_publishes_speech_endpoint_from_transcript_metadata() -> None:
    async def scenario() -> list[dict[str, object]]:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        await actions.start(bus)
        module = HearingModule(
            session_id="s",
            action_manager=actions,
            stt_driver=MockSttDriver(["hello"]),
        )
        endpoints: list[dict[str, object]] = []

        async def handler(event: Event) -> None:
            endpoints.append(event.payload)

        bus.subscribe("hearing.speech_endpoint_detected", handler)
        await module.start(bus)
        await actions.request_action(
            "listen", {"audio_path": "/tmp/roamerd-listen.wav"}, resource="microphone"
        )
        await bus.drain_once()
        await asyncio.sleep(0.01)
        return endpoints

    endpoints = asyncio.run(scenario())
    assert len(endpoints) == 1
    assert endpoints[0]["action_id"].startswith("act_")
    assert endpoints[0]["duration_sec"] == 0.0
    assert endpoints[0]["audio_path"] == "/tmp/roamerd-listen.wav"


def test_vision_cancelled_capture_cancels_active_camera_call() -> None:
    class BlockingCameraDriver(MockCameraDriver):
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.cancelled = False

        async def capture(
            self,
            *,
            output: str | None = None,
            width: int | None = None,
            height: int | None = None,
        ) -> dict[str, object]:
            self.started.set()
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            return await super().capture(output=output, width=width, height=height)

    async def scenario() -> tuple[bool, str]:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        await actions.start(bus)
        driver = BlockingCameraDriver()
        module = VisionModule(session_id="s", action_manager=actions, camera_driver=driver)
        await module.start(bus)
        bus.start_background()
        action = await actions.request_action("capture", {}, resource="camera")
        await asyncio.wait_for(driver.started.wait(), timeout=0.5)
        await actions.cancel_action(action.action_id, "client_request")
        await asyncio.sleep(0.05)
        status = actions.get_action(action.action_id)
        assert status is not None
        driver.release.set()
        await module.stop()
        await bus.stop()
        return driver.cancelled, status.status.value

    assert asyncio.run(scenario()) == (True, "cancelled")


def test_hearing_module_publishes_wake_driver_hits() -> None:
    class OneShotWakeDriver:
        def __init__(self) -> None:
            self.stopped = False
            self.count = 0

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            self.stopped = True

        async def wait_for_wake(self) -> WakePayload | None:
            self.count += 1
            if self.count == 1:
                return WakePayload(source="su03t_gpio", phrase="richard")
            await asyncio.Event().wait()
            return None

        async def health_check(self):
            from roamerd.kernel.state_manager import HealthState

            return HealthState.HEALTHY

    async def scenario() -> tuple[list[str], bool]:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        wake_driver = OneShotWakeDriver()
        module = HearingModule(
            session_id="s",
            action_manager=actions,
            stt_driver=MockSttDriver(),
            wake_driver=wake_driver,
        )
        seen: list[str] = []

        async def handler(event):
            seen.append(str(event.payload.get("source")))

        bus.subscribe("hearing.wake_triggered", handler)
        bus.start_background()
        await module.start(bus)
        await asyncio.sleep(0.01)
        await module.stop()
        await bus.stop()
        return seen, wake_driver.stopped

    assert asyncio.run(scenario()) == (["su03t_gpio"], True)


def test_hearing_module_keeps_hardware_wake_hits_during_playback() -> None:
    class QueueWakeDriver:
        def __init__(self) -> None:
            self.queue: asyncio.Queue[WakePayload] = asyncio.Queue()
            self.stopped = False

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            self.stopped = True

        async def wait_for_wake(self) -> WakePayload | None:
            return await self.queue.get()

        async def health_check(self):
            from roamerd.kernel.state_manager import HealthState

            return HealthState.HEALTHY

    async def scenario() -> list[str]:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        wake_driver = QueueWakeDriver()
        module = HearingModule(
            session_id="s",
            action_manager=actions,
            stt_driver=MockSttDriver(),
            wake_driver=wake_driver,
        )
        seen: list[str] = []

        async def handler(event: Event) -> None:
            seen.append(str(event.payload.get("phrase")))

        bus.subscribe("hearing.wake_triggered", handler)
        bus.start_background()
        await module.start(bus)
        await bus.publish(make_event("speech.playback_started", source="test", session_id="s"))
        await asyncio.sleep(0.01)
        await wake_driver.queue.put(WakePayload(source="su03t_gpio", phrase="during"))
        await asyncio.sleep(0.01)
        await bus.publish(make_event("speech.playback_completed", source="test", session_id="s"))
        await asyncio.sleep(0.01)
        await wake_driver.queue.put(WakePayload(source="su03t_gpio", phrase="after"))
        await asyncio.sleep(0.01)
        await module.stop()
        await bus.stop()
        return seen

    assert asyncio.run(scenario()) == ["during", "after"]


def test_reminder_module_schedules_non_persistent_speak_action(tmp_path: Path) -> None:
    async def scenario() -> tuple[str, list[str], list[str]]:
        bus = EventBus(session_id="s")
        actions = ActionManager(session_id="s")
        await actions.start(bus)
        reminder = ReminderModule(session_id="s", action_manager=actions)
        speech = SpeechModule(
            session_id="s",
            action_manager=actions,
            tts_driver=MockTtsDriver(),
            playback_driver=MockPlaybackDriver(),
        )
        seen: list[str] = []

        async def handler(event: Event) -> None:
            seen.append(event.event_type)

        bus.subscribe("reminder.scheduled", handler)
        bus.subscribe("reminder.triggered", handler)
        await reminder.start(bus)
        await speech.start(bus)
        action = await actions.request_action(
            "remind.schedule",
            {
                "delay_sec": 0.01,
                "text": "喝水",
                "save_path": str(tmp_path / "reminder.wav"),
            },
        )
        bus.start_background()
        await asyncio.sleep(0.05)
        await reminder.stop()
        await speech.stop()
        await bus.stop()
        scheduled = actions.get_action(action.action_id)
        assert scheduled is not None
        speak_actions = [
            item.payload.get("text")
            for item in actions.list_actions()
            if item.action_type == "speak" and item.status.value == "completed"
        ]
        return scheduled.status.value, [str(item) for item in speak_actions], seen

    assert asyncio.run(scenario()) == (
        "completed",
        ["喝水"],
        ["reminder.scheduled", "reminder.triggered"],
    )
