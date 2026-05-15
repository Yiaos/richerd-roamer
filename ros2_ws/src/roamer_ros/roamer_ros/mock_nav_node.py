"""Mock navigation node for development tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class MockMotionState:
    x: float = 0.0
    y: float = 0.0
    angle: float | None = None
    frame: str = "valetudo_pixel"
    docked: bool = False
    stopped: bool = False


def handle_motion_command(command: dict[str, Any], *, state: MockMotionState) -> dict[str, Any]:
    correlation_id = str(command.get("correlation_id", ""))
    op = str(command.get("op", ""))
    if op == "goto":
        target = command.get("target")
        if not isinstance(target, dict):
            return _response(correlation_id, ok=False, error_code="motion.request.invalid")
        state.x = float(target["x"])
        state.y = float(target["y"])
        state.angle = float(target["angle"]) if target.get("angle") is not None else None
        state.frame = str(target.get("frame", state.frame))
        state.docked = False
        return _response(correlation_id, ok=True, final_position=_position(state))
    if op == "home":
        state.docked = True
        return _response(correlation_id, ok=True, docked=True)
    if op == "stop":
        state.stopped = True
        return _response(correlation_id, ok=True)
    if op == "position":
        return _response(correlation_id, ok=True, **_position(state))
    if op == "status":
        return _response(correlation_id, ok=True, docked=state.docked, state="idle")
    return _response(correlation_id, ok=False, error_code="motion.request.invalid")


def _position(state: MockMotionState) -> dict[str, Any]:
    return {
        "x": state.x,
        "y": state.y,
        "angle": state.angle,
        "frame": state.frame,
    }


def _response(correlation_id: str, **kwargs: Any) -> dict[str, Any]:
    return {"correlation_id": correlation_id, **kwargs}


def main() -> None:
    try:
        import rclpy  # type: ignore[import-not-found]
        from rclpy.node import Node  # type: ignore[import-not-found]
        from std_msgs.msg import String  # type: ignore[import-not-found]
    except Exception:
        return
    rclpy.init()
    node = Node("mock_nav_node")
    state = MockMotionState()
    publisher = node.create_publisher(String, "/roamer/motion/response", 10)

    def on_command(message: Any) -> None:
        try:
            command = json.loads(str(message.data))
        except json.JSONDecodeError:
            return
        if not isinstance(command, dict):
            return
        response = String()
        response.data = json.dumps(handle_motion_command(command, state=state))
        publisher.publish(response)

    node.create_subscription(String, "/roamer/motion/command", on_command, 10)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
