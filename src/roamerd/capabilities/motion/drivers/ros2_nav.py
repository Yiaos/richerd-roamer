from __future__ import annotations

from dataclasses import dataclass

from roamerd.capabilities.motion.drivers.ros2_nav_base import MotionResult, MotionStatus


@dataclass
class FakeRos2MotionClient:
    state_age_sec: float = 0.0

    def __post_init__(self) -> None:
        self.commands: list[str] = []

    async def goto(self, x: float, y: float, angle: float | None = None) -> MotionResult:
        self.commands.append("goto")
        return MotionResult(status="arrived", x=x, y=y, angle=angle)

    async def home(self) -> MotionResult:
        self.commands.append("home")
        return MotionResult(status="docked")

    async def stop(self) -> None:
        self.commands.append("stop")

    async def status(self) -> MotionStatus:
        return MotionStatus(moving=False, docked=False)


class Ros2NavDriver:
    def __init__(self, *, client: FakeRos2MotionClient, max_state_age_sec: float = 10.0) -> None:
        self._client = client
        self._max_state_age_sec = max_state_age_sec

    async def goto(self, x: float, y: float, angle: float | None = None) -> MotionResult:
        self._assert_fresh_state()
        return await self._client.goto(x, y, angle)

    async def home(self) -> MotionResult:
        self._assert_fresh_state()
        return await self._client.home()

    async def stop(self) -> None:
        await self._client.stop()

    async def status(self) -> MotionStatus:
        return await self._client.status()

    def _assert_fresh_state(self) -> None:
        if self._client.state_age_sec > self._max_state_age_sec:
            raise RuntimeError("stale RobotState")
