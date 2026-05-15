"""Mock ROS2 navigation driver."""

from __future__ import annotations

from roamerd.events.motion import MotionTarget, Position
from roamerd.kernel.state_manager import HealthState


class MockRos2NavDriver:
    def __init__(self) -> None:
        self.position = Position(x=0, y=0)
        self.stopped = False
        self.moves: list[MotionTarget] = []

    async def move_to(self, target: MotionTarget) -> dict[str, object]:
        self.moves.append(target)
        self.position = Position(x=target.x, y=target.y, angle=target.angle, frame=target.frame)
        return {
            "ok": True,
            "final_position": self.position.model_dump(mode="json"),
            "duration_sec": 0.0,
        }

    async def stop(self) -> None:
        self.stopped = True

    async def dock(self) -> dict[str, object]:
        return {
            "ok": True,
            "final_position": self.position.model_dump(mode="json"),
            "duration_sec": 0.0,
            "docked": True,
        }

    async def locate(self) -> dict[str, object]:
        return {"ok": True, "capability": "LocateCapability", "action": "locate"}

    async def get_position(self) -> Position:
        return self.position

    async def get_status(self) -> dict[str, object]:
        return {"ok": True, "battery_percent": 100, "docked": False, "state": "idle"}

    async def health_check(self) -> HealthState:
        return HealthState.HEALTHY
