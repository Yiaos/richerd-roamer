"""motion.home action."""

from __future__ import annotations

import time
from typing import Any

from roamer.platform.contract import ErrorCode
from roamer.platform.output import error, success
from roamer.plugins.motion.drivers.valetudo import ValetudoMotionDriver


class MotionHomeAction:
    """Send robot home (dock) with optional wait mode."""

    def __init__(self, config: dict[str, Any]):
        self._driver = ValetudoMotionDriver(config.get("valetudo", {}))
        motion = config.get("motion", {})
        self._wait_timeout_sec = float(motion.get("wait_timeout_sec", 300))
        self._poll_interval_sec = float(motion.get("poll_interval_sec", 2))

    def run(self, wait: bool = False) -> dict[str, Any]:
        command_result = self._driver.home()
        if not command_result.get("ok"):
            return command_result

        if not wait:
            return success(
                accepted=True,
                waiting=False,
                action="home",
                response=command_result.get("response"),
            )

        start = time.monotonic()
        while time.monotonic() - start <= self._wait_timeout_sec:
            status_result = self._driver.get_status()
            if status_result.get("ok"):
                status = str(status_result.get("status") or "").lower()
                if status == "docked":
                    return success(
                        accepted=True,
                        waiting=True,
                        status="docked",
                        battery_percent=status_result.get("battery_percent"),
                        elapsed_sec=round(time.monotonic() - start, 2),
                    )
                if status == "error":
                    return error(
                        "motion_home_failed",
                        "Robot entered error state while returning to dock",
                        error_code="motion.home.failed",
                        status="error",
                        elapsed_sec=round(time.monotonic() - start, 2),
                    )

            time.sleep(self._poll_interval_sec)

        return error(
            "motion_home_timeout",
            "Timed out waiting for robot to dock",
            error_code=ErrorCode.MOTION_HOME_TIMEOUT,
            timeout_sec=self._wait_timeout_sec,
        )
