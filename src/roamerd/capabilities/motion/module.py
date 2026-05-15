"""Motion module backed by a ROS2 navigation driver."""

from __future__ import annotations

import asyncio
import math
from contextlib import suppress
from typing import Protocol, runtime_checkable

from roamerd.events.base import Event, Priority, make_event
from roamerd.events.motion import MotionTarget, Position
from roamerd.kernel.action_manager import ActionManager
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.state_manager import HealthState


@runtime_checkable
class MotionDriver(Protocol):
    async def move_to(self, target: MotionTarget) -> dict[str, object]: ...

    async def stop(self) -> None: ...

    async def dock(self) -> dict[str, object]: ...

    async def locate(self) -> dict[str, object]: ...

    async def get_position(self) -> Position: ...

    async def get_status(self) -> dict[str, object]: ...

    async def health_check(self) -> HealthState: ...


class MotionModule:
    name = "motion"
    resource = "motion"
    events_produced = [
        "motion.started",
        "motion.completed",
        "motion.failed",
        "motion.position_updated",
        "motion.status_updated",
    ]
    events_consumed = [
        "action.started",
        "action.cancelled",
        "action.preempted",
        "motion.stop_requested",
        "safety.emergency_stop_requested",
        "safety.triggered",
        "system.shutdown_requested",
    ]

    def __init__(
        self,
        *,
        session_id: str,
        action_manager: ActionManager,
        driver: MotionDriver,
        wait_timeout_sec: float = 300.0,
        poll_interval_sec: float = 2.0,
        arrival_tolerance: float = 150.0,
    ) -> None:
        self._session_id = session_id
        self._actions = action_manager
        self._driver = driver
        self._wait_timeout_sec = wait_timeout_sec
        self._poll_interval_sec = poll_interval_sec
        self._arrival_tolerance = arrival_tolerance
        self._bus: EventBus | None = None
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def start(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe("action.started", self._on_action_started)
        bus.subscribe("action.cancelled", self._on_action_stopped)
        bus.subscribe("action.preempted", self._on_action_stopped)
        bus.subscribe("motion.stop_requested", self._on_stop)
        bus.subscribe("safety.emergency_stop_requested", self._on_stop)
        bus.subscribe("safety.triggered", self._on_stop)
        bus.subscribe("system.shutdown_requested", self._on_shutdown_requested)
        await bus.publish(
            make_event(
                "system.module_ready",
                source="motion_module",
                session_id=self._session_id,
                payload={"name": self.name, "component_type": "module", "state": "healthy"},
            )
        )

    async def stop(self) -> None:
        await self._driver.stop()
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()

    async def health_check(self) -> HealthState:
        return await self._driver.health_check()

    async def _on_action_started(self, event: Event) -> None:
        if (
            event.payload.get("action_type")
            not in {
                "motion.goto",
                "motion.home",
                "motion.locate",
                "motion.position",
                "motion.status",
            }
            or self._bus is None
        ):
            return
        action_id = event.action_id or ""
        task = asyncio.create_task(self._run_motion(event))
        self._tasks[action_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(action_id, None))

    async def _run_motion(self, event: Event) -> None:
        if self._bus is None:
            return
        action_id = event.action_id or ""
        action_type = str(event.payload.get("action_type"))
        await self._bus.publish(
            make_event(
                "motion.started",
                source="motion_module",
                session_id=self._session_id,
                action_id=action_id,
                payload={"action_id": action_id},
                priority=Priority.NORMAL,
            )
        )
        try:
            args = event.payload.get("payload")
            payload = args if isinstance(args, dict) else {}
            if action_type == "motion.home":
                result = await self._driver.dock()
                if result.get("ok", False) and bool(payload.get("wait", True)):
                    result = await self._wait_until_docked(result)
            elif action_type == "motion.locate":
                result = await self._driver.locate()
            elif action_type == "motion.position":
                position = await self._driver.get_position()
                result = {"ok": True, "position": position.model_dump(mode="json")}
            elif action_type == "motion.status":
                result = await self._driver.get_status()
            else:
                raw_target = payload.get("target", payload)
                target = MotionTarget.model_validate(raw_target)
                frame_error = await self._validate_target_frame(target)
                if frame_error is not None:
                    result = frame_error
                else:
                    result = await self._driver.move_to(target)
                    if result.get("ok", False) and bool(payload.get("wait", True)):
                        result = await self._wait_until_target(target, result)
        except Exception as exc:
            result = {"ok": False, "error": str(exc), "error_code": "motion.ros2.unavailable"}
        if result.get("ok", False):
            position_raw = result.get("final_position") or result.get("position")
            if isinstance(position_raw, dict):
                await self._bus.publish(
                    make_event(
                        "motion.position_updated",
                        source="motion_module",
                        session_id=self._session_id,
                        payload={"position": position_raw},
                    )
                )
            status_payload = _motion_status_payload(result)
            if status_payload:
                await self._bus.publish(
                    make_event(
                        "motion.status_updated",
                        source="motion_module",
                        session_id=self._session_id,
                        payload=status_payload,
                        priority=Priority.LOW,
                    )
                )
            await self._bus.publish(
                make_event(
                    "motion.completed",
                    source="motion_module",
                    session_id=self._session_id,
                    action_id=action_id,
                    payload={"action_id": action_id, "result": result},
                )
            )
            await self._actions.complete_action(action_id, _json_dict(result))
        else:
            error = {
                "error_code": str(result.get("error_code", "motion.failed")),
                "error_message": str(result.get("error", "")),
            }
            await self._bus.publish(
                make_event(
                    "motion.failed",
                    source="motion_module",
                    session_id=self._session_id,
                    action_id=action_id,
                    payload=error,
                )
            )
            await self._actions.fail_action(action_id, error)

    async def _on_stop(self, event: Event) -> None:
        await self._driver.stop()
        if self._bus is not None:
            await self._bus.publish(
                make_event(
                    "safety.stop_applied",
                    source="motion_module",
                    session_id=self._session_id,
                    payload={
                        "reason": str(event.payload.get("reason", "stop_requested")),
                        "source_event": event.event_type,
                    },
                    priority=Priority.CRITICAL,
                )
            )

    async def _on_shutdown_requested(self, event: Event) -> None:
        await self.stop()

    async def _on_action_stopped(self, event: Event) -> None:
        if str(event.payload.get("action_type", "")).startswith("motion."):
            await self._driver.stop()
            task = self._tasks.get(event.action_id or "")
            if task is not None:
                task.cancel()

    async def _validate_target_frame(self, target: MotionTarget) -> dict[str, object] | None:
        position = await self._driver.get_position()
        if position.frame == target.frame:
            return None
        return {
            "ok": False,
            "error": f"target frame {target.frame} does not match robot frame {position.frame}",
            "error_code": "motion.frame_mismatch",
        }

    async def _wait_until_target(
        self, target: MotionTarget, result: dict[str, object]
    ) -> dict[str, object]:
        deadline = asyncio.get_running_loop().time() + self._wait_timeout_sec
        while True:
            position = await self._driver.get_position()
            if _target_reached(position, target, self._arrival_tolerance):
                return {**result, "final_position": position.model_dump(mode="json")}
            if asyncio.get_running_loop().time() >= deadline:
                return {
                    "ok": False,
                    "error": "motion target was not reached before timeout",
                    "error_code": "motion.timeout",
                    "last_position": position.model_dump(mode="json"),
                }
            await asyncio.sleep(self._poll_interval_sec)

    async def _wait_until_docked(self, result: dict[str, object]) -> dict[str, object]:
        deadline = asyncio.get_running_loop().time() + self._wait_timeout_sec
        while True:
            status = await self._driver.get_status()
            if status.get("docked") is True:
                return {**result, "docked": True, "status": status}
            if asyncio.get_running_loop().time() >= deadline:
                return {
                    "ok": False,
                    "error": "robot did not dock before timeout",
                    "error_code": "motion.timeout",
                    "last_status": status,
                }
            await asyncio.sleep(self._poll_interval_sec)


def _json_dict(value: dict[str, object]) -> dict[str, object]:
    return value


def _target_reached(position: Position, target: MotionTarget, tolerance: float) -> bool:
    return math.hypot(position.x - target.x, position.y - target.y) <= tolerance


def _motion_status_payload(result: dict[str, object]) -> dict[str, object]:
    return {
        key: result[key]
        for key in ("battery_percent", "docked", "state")
        if key in result and result[key] is not None
    }
