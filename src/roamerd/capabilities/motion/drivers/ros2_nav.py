"""ROS2 navigation driver.

The driver talks to the ROS2 substrate through command/response topics. The
Valetudo HTTP implementation remains inside ``ros2_ws`` bridge nodes.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from roamerd.events.motion import MotionTarget, Position
from roamerd.kernel.state_manager import HealthState


@runtime_checkable
class Ros2MotionClient(Protocol):
    async def goto(self, target: MotionTarget) -> dict[str, object]: ...

    async def home(self) -> dict[str, object]: ...

    async def locate(self) -> dict[str, object]: ...

    async def stop(self) -> dict[str, object]: ...

    async def get_position(self) -> Position: ...

    async def get_status(self) -> dict[str, object]: ...

    async def health_check(self) -> HealthState: ...


class Ros2NavDriver:
    def __init__(
        self,
        *,
        client: Ros2MotionClient | None = None,
        client_factory: Callable[[], Ros2MotionClient] | None = None,
    ) -> None:
        self._client: Ros2MotionClient | None = client
        self._client_factory = client_factory or RclpyJsonMotionClient
        self._startup_error: str | None = None

    async def move_to(self, target: MotionTarget) -> dict[str, object]:
        client = self._get_client()
        if client is None:
            return self._unavailable()
        return await client.goto(target)

    async def stop(self) -> None:
        client = self._get_client()
        if client is not None:
            await client.stop()

    async def dock(self) -> dict[str, object]:
        client = self._get_client()
        if client is None:
            return self._unavailable()
        return await client.home()

    async def locate(self) -> dict[str, object]:
        client = self._get_client()
        if client is None:
            return self._unavailable()
        return await client.locate()

    async def get_position(self) -> Position:
        client = self._get_client()
        if client is None:
            raise RuntimeError(self._startup_error or "ROS2 navigation is unavailable")
        return await client.get_position()

    async def get_status(self) -> dict[str, object]:
        client = self._get_client()
        if client is None:
            return self._unavailable()
        return await client.get_status()

    async def health_check(self) -> HealthState:
        client = self._get_client()
        if client is None:
            return HealthState.UNAVAILABLE
        return await client.health_check()

    def _get_client(self) -> Ros2MotionClient | None:
        if self._client is not None:
            return self._client
        try:
            self._client = self._client_factory()
        except Exception as exc:
            self._startup_error = str(exc)
            return None
        return self._client

    def _unavailable(self) -> dict[str, object]:
        return {
            "ok": False,
            "error": self._startup_error or "ROS2 navigation is unavailable",
            "error_code": "motion.ros2.unavailable",
        }


class RclpyJsonMotionClient:
    def __init__(
        self,
        *,
        command_topic: str = "/roamer/motion/command",
        response_topic: str = "/roamer/motion/response",
        timeout_sec: float = 30.0,
    ) -> None:
        import rclpy  # type: ignore[import-not-found]
        from rclpy.node import Node  # type: ignore[import-not-found]
        from std_msgs.msg import String  # type: ignore[import-not-found]

        self._rclpy = rclpy
        self._string_cls = String
        self._timeout_sec = timeout_sec
        if not rclpy.ok():
            rclpy.init(args=None)
        self._node: Any = Node("roamerd_motion_client")
        self._publisher = self._node.create_publisher(String, command_topic, 10)
        self._pending: dict[
            str, tuple[asyncio.AbstractEventLoop, asyncio.Future[dict[str, Any]]]
        ] = {}
        self._node.create_subscription(String, response_topic, self._on_response, 10)

    async def goto(self, target: MotionTarget) -> dict[str, object]:
        return await self._request(
            {
                "op": "goto",
                "target": target.model_dump(mode="json"),
            }
        )

    async def home(self) -> dict[str, object]:
        return await self._request({"op": "home"})

    async def locate(self) -> dict[str, object]:
        return await self._request({"op": "locate"})

    async def stop(self) -> dict[str, object]:
        return await self._request({"op": "stop"})

    async def get_position(self) -> Position:
        result = await self._request({"op": "position"})
        if not result.get("ok"):
            raise RuntimeError(str(result.get("error", "position unavailable")))
        return Position.model_validate(result)

    async def get_status(self) -> dict[str, object]:
        return await self._request({"op": "status"})

    async def health_check(self) -> HealthState:
        result = await self._request({"op": "status"}, timeout_sec=2.0)
        return HealthState.HEALTHY if result.get("ok") else HealthState.UNAVAILABLE

    async def _request(
        self, payload: dict[str, Any], *, timeout_sec: float | None = None
    ) -> dict[str, object]:
        correlation_id = uuid4().hex[:12]
        payload = {**payload, "correlation_id": correlation_id}
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[correlation_id] = (loop, future)
        message = self._string_cls()
        message.data = json.dumps(payload)
        self._publisher.publish(message)
        deadline = loop.time() + (timeout_sec or self._timeout_sec)
        while not future.done():
            remaining = deadline - loop.time()
            if remaining <= 0:
                self._pending.pop(correlation_id, None)
                return {
                    "ok": False,
                    "error": "ROS2 motion response timed out",
                    "error_code": "motion.ros2.timeout",
                }
            await asyncio.to_thread(
                self._rclpy.spin_once, self._node, timeout_sec=min(0.05, remaining)
            )
        return await future

    def _on_response(self, message: Any) -> None:
        try:
            payload = json.loads(str(message.data))
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict):
            return
        correlation_id = str(payload.get("correlation_id", ""))
        pending = self._pending.pop(correlation_id, None)
        if pending is None:
            return
        loop, future = pending
        if not future.done():
            loop.call_soon_threadsafe(future.set_result, payload)
