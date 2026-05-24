from __future__ import annotations

from roamerd.capabilities.motion.drivers.mock_ros2 import MockRos2NavDriver
from roamerd.capabilities.motion.drivers.ros2_nav_base import MotionDriver, MotionResult
from roamerd.events import Event, Priority
from roamerd.kernel import ActionManager, EventBus
from roamerd.types import JSONDict


class MotionModule:
    name = "motion"
    events_produced = [
        "motion.started",
        "motion.completed",
        "motion.failed",
        "motion.stop_requested",
    ]
    events_consumed = [
        "action.started",
        "action.preempt_requested",
        "safety.emergency_stop_requested",
        "safety.triggered",
    ]
    resources = ["motion"]

    def __init__(
        self,
        *,
        driver: MotionDriver,
        action_manager: ActionManager | None = None,
        session_id: str = "session-1",
    ) -> None:
        self._driver = driver
        self._actions = action_manager
        self._session_id = session_id
        self._bus: EventBus | None = None

    async def start(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe("action.started", self._handle_action_started)
        bus.subscribe("action.preempt_requested", self._handle_preempt_requested)
        bus.subscribe("safety.emergency_stop_requested", self._handle_safety_stop)
        bus.subscribe("safety.triggered", self._handle_safety_stop)

    async def stop(self) -> None:
        await self._driver.stop()

    async def health_check(self) -> str:
        return "healthy"

    async def _handle_action_started(self, event: Event) -> None:
        action_type = event.payload.get("action_type")
        if action_type not in {"motion.home", "motion.goto"}:
            return
        action_id = event.action_id or str(event.payload.get("action_id", ""))
        await self._publish(
            "motion.started",
            {"action_id": action_id, "action_type": str(action_type)},
            action_id=action_id,
            turn_id=event.turn_id,
            priority=Priority.HIGH,
        )
        try:
            result = await self._run_motion(action_id, str(action_type))
            if _completes_immediately(self._driver):
                await self._publish_completed(action_id, result, event.turn_id)
                if self._actions is not None:
                    await self._actions.complete_action(action_id, result.model_dump(mode="json"))
        except Exception as exc:
            await self._publish(
                "motion.failed",
                {"action_id": action_id, "message": str(exc)},
                action_id=action_id,
                turn_id=event.turn_id,
            )
            if self._actions is not None:
                await self._actions.fail_action(action_id, {"message": str(exc)})

    async def _run_motion(self, action_id: str, action_type: str) -> MotionResult:
        action = self._actions.get_action(action_id) if self._actions is not None else None
        if action_type == "motion.home":
            return await self._driver.home()
        target = action.payload.get("target", {}) if action is not None else {}
        if not isinstance(target, dict):
            target = {}
        return await self._driver.goto(
            _float_value(target.get("x")),
            _float_value(target.get("y")),
            _optional_float_value(target.get("angle")),
        )

    async def _handle_preempt_requested(self, event: Event) -> None:
        action_id = event.action_id or str(event.payload.get("action_id", ""))
        action = self._actions.get_action(action_id) if self._actions is not None else None
        if action is None or action.resource != "motion":
            return
        await self._driver.stop()
        if self._actions is not None:
            await self._actions.mark_preempted(action_id, str(event.payload.get("reason", "")))

    async def _handle_safety_stop(self, event: Event) -> None:
        await self._driver.stop()
        await self._publish(
            "motion.stop_requested",
            {"reason": event.event_type},
            action_id=event.action_id,
            turn_id=event.turn_id,
            priority=Priority.CRITICAL,
        )

    async def _publish_completed(
        self,
        action_id: str,
        result: MotionResult,
        turn_id: str | None,
    ) -> None:
        await self._publish(
            "motion.completed",
            {"action_id": action_id, **result.model_dump(mode="json")},
            action_id=action_id,
            turn_id=turn_id,
            priority=Priority.HIGH,
        )

    async def _publish(
        self,
        event_type: str,
        payload: JSONDict,
        *,
        action_id: str | None,
        turn_id: str | None,
        priority: Priority = Priority.NORMAL,
    ) -> None:
        if self._bus is None:
            return
        await self._bus.publish(
            Event(
                event_type=event_type,
                source="motion",
                session_id=self._session_id,
                action_id=action_id,
                turn_id=turn_id,
                priority=priority,
                payload=payload,
            )
        )


def _completes_immediately(driver: MotionDriver) -> bool:
    return not isinstance(driver, MockRos2NavDriver) or driver.complete_immediately


def _float_value(value: object) -> float:
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _optional_float_value(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None
