import pytest

from roamerd.capabilities.motion.drivers.ros2_nav import FakeRos2MotionClient, Ros2NavDriver


@pytest.mark.asyncio
async def test_ros2_nav_driver_uses_roamer_motion_contract() -> None:
    client = FakeRos2MotionClient()
    driver = Ros2NavDriver(client=client, max_state_age_sec=10)

    goto = await driver.goto(1, 2, 0.5)
    home = await driver.home()
    status = await driver.status()

    assert goto.status == "arrived"
    assert home.status == "docked"
    assert status.moving is False
    assert client.commands == ["goto", "home"]


@pytest.mark.asyncio
async def test_ros2_nav_driver_rejects_stale_robot_state_for_new_motion() -> None:
    client = FakeRos2MotionClient(state_age_sec=20)
    driver = Ros2NavDriver(client=client, max_state_age_sec=10)

    with pytest.raises(RuntimeError, match="stale RobotState"):
        await driver.goto(1, 2)


@pytest.mark.asyncio
async def test_ros2_nav_stop_allowed_even_when_state_is_stale() -> None:
    client = FakeRos2MotionClient(state_age_sec=20)
    driver = Ros2NavDriver(client=client, max_state_age_sec=10)

    await driver.stop()

    assert client.commands == ["stop"]
