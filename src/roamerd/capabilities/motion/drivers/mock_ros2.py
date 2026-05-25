from __future__ import annotations

from roamerd.capabilities.motion.drivers.ros2_nav_base import MotionResult, MotionStatus


class MockRos2NavDriver:
    def __init__(self, *, complete_immediately: bool = True) -> None:
        self.complete_immediately = complete_immediately
        self.completes_synchronously = complete_immediately
        self.homed = False
        self.stopped = False
        self.target: tuple[float, float, float | None] | None = None

    async def goto(self, x: float, y: float, angle: float | None = None) -> MotionResult:
        self.target = (x, y, angle)
        return MotionResult(status="arrived", x=x, y=y, angle=angle)

    async def home(self) -> MotionResult:
        self.homed = True
        return MotionResult(status="docked")

    async def stop(self) -> None:
        self.stopped = True

    async def status(self) -> MotionStatus:
        return MotionStatus(moving=not self.complete_immediately, docked=self.homed)
