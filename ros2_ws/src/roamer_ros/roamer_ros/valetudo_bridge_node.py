"""Valetudo-to-ROS2 bridge support.

The HTTP-facing Valetudo implementation lives in the ROS2 substrate package,
not in ``src/roamerd``. The node entry point is intentionally light so the
client can be unit-tested without a ROS2 installation.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import request as urllib_request

UrlOpen = Callable[..., Any]


class ValetudoClient:
    """Small Valetudo v2 HTTP client used by the ROS2 bridge node."""

    def __init__(
        self,
        *,
        host: str,
        port: int = 80,
        timeout_sec: float = 8.0,
        urlopen: UrlOpen | None = None,
    ) -> None:
        if not host.strip():
            raise ValueError("host is required")
        if port <= 0:
            raise ValueError("port must be > 0")
        self._host = host.strip()
        self._port = port
        self._timeout_sec = timeout_sec
        self._urlopen = urlopen or urllib_request.urlopen

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self._port}"

    def get_capabilities(self) -> dict[str, Any]:
        response = self._request_json("GET", "/api/v2/robot/capabilities")
        if not response.get("ok"):
            return response
        data = response.get("data")
        if not isinstance(data, list):
            return _error("motion.request.failed", "Unexpected capabilities response")
        return {"ok": True, "capabilities": data}

    def get_state(self) -> dict[str, Any]:
        response = self._request_json("GET", "/api/v2/robot/state")
        if not response.get("ok"):
            return response
        data = response.get("data")
        if not isinstance(data, dict):
            return _error("motion.request.failed", "Unexpected robot state payload")
        return {"ok": True, "state": data}

    def get_status(self) -> dict[str, Any]:
        state_result = self.get_state()
        if not state_result.get("ok"):
            return state_result
        state = state_result["state"]
        return {
            "ok": True,
            "status": extract_status(state),
            "battery_percent": extract_battery(state),
            "map_ready": isinstance(state.get("map"), dict),
        }

    def get_position(self) -> dict[str, Any]:
        state_result = self.get_state()
        if not state_result.get("ok"):
            return state_result
        position = extract_robot_position(state_result["state"])
        if position is None:
            return _error("motion.position.unavailable", "Robot position unavailable")
        return {"ok": True, **position}

    def locate(self) -> dict[str, Any]:
        return self._invoke_capability("LocateCapability", {"action": "locate"})

    def home(self) -> dict[str, Any]:
        return self._invoke_capability("BasicControlCapability", {"action": "home"})

    def stop(self) -> dict[str, Any]:
        return self._invoke_capability("BasicControlCapability", {"action": "stop"})

    def goto(self, *, x: int, y: int, angle: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"action": "goto", "coordinates": {"x": int(x), "y": int(y)}}
        if angle is not None:
            payload["angle"] = int(angle)
        return self._invoke_capability("GoToLocationCapability", payload)

    def _invoke_capability(self, capability: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request_json("PUT", f"/api/v2/robot/capabilities/{capability}", payload)
        if not response.get("ok"):
            return response
        return {
            "ok": True,
            "capability": capability,
            "action": payload.get("action"),
            "response": response.get("data"),
        }

    def _request_json(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        data: bytes | None = None
        headers: dict[str, str] = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib_request.Request(
            url=f"{self.base_url}{path}", method=method, data=data, headers=headers
        )
        try:
            with self._urlopen(request, timeout=self._timeout_sec) as response:
                status_code = getattr(response, "status", response.getcode())
                raw = response.read().decode("utf-8", errors="replace")
        except urllib_error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")[:500]
            return _error(
                "motion.request.failed",
                f"HTTP {exc.code} for {path}",
                path=path,
                status_code=exc.code,
                details=details,
            )
        except urllib_error.URLError as exc:
            return _error(
                "motion.request.failed",
                f"Failed to reach Valetudo: {exc.reason}",
                path=path,
            )
        parsed: Any = None
        if raw.strip():
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw.strip()
        return {"ok": True, "path": path, "status_code": status_code, "data": parsed}


def extract_status(state: dict[str, Any]) -> str | None:
    for attribute in state.get("attributes", []):
        if not isinstance(attribute, dict) or attribute.get("__class") != "StatusStateAttribute":
            continue
        for key in ("value", "status", "state"):
            value = attribute.get(key)
            if value:
                return str(value)
    return None


def extract_battery(state: dict[str, Any]) -> int | None:
    for attribute in state.get("attributes", []):
        if not isinstance(attribute, dict) or attribute.get("__class") != "BatteryStateAttribute":
            continue
        for key in ("value", "level", "battery", "percentage"):
            value = attribute.get(key)
            if isinstance(value, (int, float)):
                return int(value)
    return None


def extract_robot_position(state: dict[str, Any]) -> dict[str, int] | None:
    entities = state.get("map", {}).get("entities", [])
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        if entity.get("__class") != "PointMapEntity" or entity.get("type") != "robot_position":
            continue
        points = entity.get("points")
        if not isinstance(points, list) or len(points) < 2:
            continue
        return {
            "x": int(points[0]),
            "y": int(points[1]),
            "angle": int(entity.get("metaData", {}).get("angle", 0)),
        }
    return None


def distance_to_target(position: dict[str, int], target_x: int, target_y: int) -> float:
    return math.hypot(position["x"] - target_x, position["y"] - target_y)


def _error(code: str, message: str, **kwargs: Any) -> dict[str, Any]:
    return {"ok": False, "error_code": code, "error_message": message, **kwargs}


def handle_motion_command(command: dict[str, Any], *, client: ValetudoClient) -> dict[str, Any]:
    correlation_id = str(command.get("correlation_id", ""))
    op = str(command.get("op", ""))
    try:
        if op == "goto":
            target = command.get("target")
            if not isinstance(target, dict):
                return _with_correlation(
                    _error("motion.request.invalid", "goto requires target"), correlation_id
                )
            response = client.goto(
                x=int(target["x"]),
                y=int(target["y"]),
                angle=int(target["angle"]) if target.get("angle") is not None else None,
            )
        elif op == "home":
            response = client.home()
        elif op == "stop":
            response = client.stop()
        elif op == "locate":
            response = client.locate()
        elif op == "position":
            response = client.get_position()
        elif op == "status":
            response = client.get_status()
        else:
            response = _error("motion.request.invalid", f"unsupported op: {op}")
    except Exception as exc:
        response = _error("motion.request.failed", str(exc))
    return _with_correlation(response, correlation_id)


def _with_correlation(response: dict[str, Any], correlation_id: str) -> dict[str, Any]:
    return {**response, "correlation_id": correlation_id}


def main() -> None:
    try:
        import rclpy  # type: ignore[import-not-found]
        from rclpy.node import Node  # type: ignore[import-not-found]
        from std_msgs.msg import String  # type: ignore[import-not-found]
    except Exception:
        return
    rclpy.init()
    node = Node("valetudo_bridge_node")
    client = ValetudoClient(
        host=os.getenv("ROAMER_VALETUDO_HOST", "10.0.0.226"),
        port=int(os.getenv("ROAMER_VALETUDO_PORT", "80")),
        timeout_sec=float(os.getenv("ROAMER_VALETUDO_TIMEOUT_SEC", "8.0")),
    )
    publisher = node.create_publisher(String, "/roamer/motion/response", 10)

    def on_command(message: Any) -> None:
        try:
            command = json.loads(str(message.data))
        except json.JSONDecodeError:
            return
        if not isinstance(command, dict):
            return
        response = String()
        response.data = json.dumps(handle_motion_command(command, client=client))
        publisher.publish(response)

    node.create_subscription(String, "/roamer/motion/command", on_command, 10)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
