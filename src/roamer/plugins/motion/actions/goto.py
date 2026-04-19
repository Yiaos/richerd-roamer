"""motion.goto action."""

from __future__ import annotations

import time
from typing import Any

from roamer.platform.contract import ErrorCode
from roamer.platform.output import error, success
from roamer.plugins.motion.drivers.valetudo import ValetudoMotionDriver


class MotionGotoAction:
    """Navigate robot to map coordinates with optional wait mode."""

    def __init__(self, config: dict[str, Any]):
        self._driver = ValetudoMotionDriver(config.get("valetudo", {}))
        motion = config.get("motion", {})
        self._wait_timeout_sec = float(motion.get("wait_timeout_sec", 300))
        self._poll_interval_sec = float(motion.get("poll_interval_sec", 2))
        self._arrival_tolerance = int(motion.get("arrival_tolerance", 150))

    def run(self, x: int, y: int, angle: int | None = None, wait: bool = False) -> dict[str, Any]:
        guard_result = self._check_guard()
        if not guard_result.get("ok"):
            return guard_result

        command_result = self._driver.goto(x=x, y=y, angle=angle)
        if not command_result.get("ok"):
            return command_result

        if not wait:
            return success(
                accepted=True,
                waiting=False,
                action="goto",
                target={"x": int(x), "y": int(y), "angle": int(angle) if angle is not None else None},
                response=command_result.get("response"),
            )

        start = time.monotonic()
        last_status: str | None = None
        last_distance: float | None = None

        while time.monotonic() - start <= self._wait_timeout_sec:
            status_result = self._driver.get_status()
            if status_result.get("ok"):
                last_status = str(status_result.get("status") or "").lower() or None
                if last_status == "error":
                    return error(
                        "motion_goto_failed",
                        "Robot entered error state during goto",
                        error_code=ErrorCode.MOTION_GOTO_GUARD_FAILED,
                        status="error",
                    )

                position_result = self._driver.get_position()
                if position_result.get("ok"):
                    position = {
                        "x": int(position_result["x"]),
                        "y": int(position_result["y"]),
                        "angle": int(position_result.get("angle", 0)),
                    }
                    last_distance = self._driver.distance_to_target(position, int(x), int(y))

                    reached = last_distance <= self._arrival_tolerance
                    if last_status in {"idle", "docked"} and reached:
                        return success(
                            accepted=True,
                            waiting=True,
                            target={"x": int(x), "y": int(y), "angle": int(angle) if angle is not None else None},
                            position=position,
                            status=last_status,
                            distance=round(last_distance, 2),
                            arrival_tolerance=self._arrival_tolerance,
                            elapsed_sec=round(time.monotonic() - start, 2),
                        )

            time.sleep(self._poll_interval_sec)

        return error(
            "motion_goto_timeout",
            "Timed out waiting for robot to reach target",
            error_code=ErrorCode.MOTION_GOTO_TIMEOUT,
            target={"x": int(x), "y": int(y), "angle": int(angle) if angle is not None else None},
            timeout_sec=self._wait_timeout_sec,
            arrival_tolerance=self._arrival_tolerance,
            last_status=last_status,
            last_distance=round(last_distance, 2) if last_distance is not None else None,
        )

    def _check_guard(self) -> dict[str, Any]:
        capability = self._driver.has_capability("GoToLocationCapability")
        if not capability.get("ok"):
            return self._guard_failed("capability_check_failed", capability.get("message"))
        if not capability.get("available"):
            return self._guard_failed(
                "capability_unavailable",
                "GoToLocationCapability is unavailable",
            )

        status_result = self._driver.get_status()
        if not status_result.get("ok"):
            return self._guard_failed("state_unavailable", status_result.get("message"))

        status = str(status_result.get("status") or "").lower()
        if status in {"returning", "cleaning", "error"}:
            return self._guard_failed("status_blocked", f"Navigation blocked while status={status}")

        position_result = self._driver.get_position()
        if not position_result.get("ok"):
            return self._guard_failed("position_unavailable", position_result.get("message"))

        return success(guard_passed=True)

    def _guard_failed(self, guard: str, message: str | None = None) -> dict[str, Any]:
        return error(
            "motion_goto_guard_failed",
            message or f"Goto guard failed: {guard}",
            error_code=ErrorCode.MOTION_GOTO_GUARD_FAILED,
            guard=guard,
        )
