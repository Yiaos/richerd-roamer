import sys
from pathlib import Path

ROS_PACKAGE = Path(__file__).resolve().parents[3] / "ros2_ws" / "src" / "roamer_ros"
sys.path.insert(0, str(ROS_PACKAGE))

from roamer_ros.mock_nav_node import MockMotionState, handle_motion_command  # noqa: E402


def test_mock_nav_node_handles_goto_and_position() -> None:
    state = MockMotionState()

    goto = handle_motion_command(
        {"op": "goto", "correlation_id": "c1", "target": {"x": 10, "y": 20}},
        state=state,
    )
    position = handle_motion_command({"op": "position", "correlation_id": "c2"}, state=state)

    assert goto["ok"] is True
    assert position == {
        "ok": True,
        "correlation_id": "c2",
        "x": 10.0,
        "y": 20.0,
        "angle": None,
        "frame": "valetudo_pixel",
    }
