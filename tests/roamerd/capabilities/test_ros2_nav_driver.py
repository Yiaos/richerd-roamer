import asyncio

from roamerd.capabilities.motion.drivers.ros2_nav import Ros2NavDriver
from roamerd.events.motion import MotionTarget, Position
from roamerd.kernel.state_manager import HealthState


class FakeRos2MotionClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def goto(self, target: MotionTarget) -> dict[str, object]:
        self.calls.append(("goto", target))
        return {"ok": True, "final_position": {"x": target.x, "y": target.y}}

    async def home(self) -> dict[str, object]:
        self.calls.append(("home", {}))
        return {"ok": True, "docked": True}

    async def locate(self) -> dict[str, object]:
        self.calls.append(("locate", {}))
        return {"ok": True, "capability": "LocateCapability", "action": "locate"}

    async def stop(self) -> dict[str, object]:
        self.calls.append(("stop", {}))
        return {"ok": True}

    async def get_position(self) -> Position:
        self.calls.append(("position", {}))
        return Position(x=1, y=2, angle=3)

    async def get_status(self) -> dict[str, object]:
        self.calls.append(("status", {}))
        return {"ok": True, "battery_percent": 90}

    async def health_check(self) -> HealthState:
        return HealthState.HEALTHY


def test_ros2_nav_driver_delegates_motion_commands_to_ros_client() -> None:
    async def scenario() -> tuple[dict[str, object], dict[str, object], Position, list[str]]:
        client = FakeRos2MotionClient()
        driver = Ros2NavDriver(client=client)
        move = await driver.move_to(MotionTarget(x=10, y=20, angle=90))
        dock = await driver.dock()
        locate = await driver.locate()
        await driver.stop()
        position = await driver.get_position()
        return move, dock, locate, position, [call[0] for call in client.calls]

    move, dock, locate, position, calls = asyncio.run(scenario())

    assert move["ok"] is True
    assert dock["docked"] is True
    assert locate["action"] == "locate"
    assert position == Position(x=1, y=2, angle=3)
    assert calls == ["goto", "home", "locate", "stop", "position"]


def test_ros2_nav_driver_reports_unavailable_when_ros_client_cannot_start() -> None:
    async def scenario() -> tuple[dict[str, object], HealthState]:
        driver = Ros2NavDriver(client_factory=lambda: (_ for _ in ()).throw(RuntimeError("no ros")))
        return await driver.move_to(MotionTarget(x=1, y=2)), await driver.health_check()

    result, health = asyncio.run(scenario())

    assert result["ok"] is False
    assert result["error_code"] == "motion.ros2.unavailable"
    assert health == HealthState.UNAVAILABLE
