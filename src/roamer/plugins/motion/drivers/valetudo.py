"""Valetudo-backed motion driver."""

from __future__ import annotations

import json
import math
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import request as urllib_request

from roamer.platform.contract import ErrorCode
from roamer.platform.output import error, success

UrlOpen = Callable[..., Any]


class ValetudoMotionDriver:
    """Driver for Roamer motion capability using Valetudo v2 HTTP APIs."""

    def __init__(self, config: dict[str, Any], urlopen: UrlOpen | None = None):
        self._config = config

        raw_host = config.get("host")
        if raw_host is None or not str(raw_host).strip():
            raise ValueError("valetudo.host is required")

        raw_port = config.get("port")
        if raw_port is None:
            raise ValueError("valetudo.port is required")

        try:
            port = int(raw_port)
        except (TypeError, ValueError) as exc:
            raise ValueError("valetudo.port must be an integer") from exc
        if port <= 0:
            raise ValueError("valetudo.port must be > 0")

        self._host = str(raw_host).strip()
        self._port = port
        self._timeout_sec = float(config.get("timeout_sec", 8.0))
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
            return error(
                "motion_request_failed",
                "Unexpected capabilities response",
                error_code="motion.request.failed",
                path="/api/v2/robot/capabilities",
            )

        return success(capabilities=data)

    def has_capability(self, capability_name: str) -> dict[str, Any]:
        capabilities_result = self.get_capabilities()
        if not capabilities_result.get("ok"):
            return capabilities_result

        capabilities = capabilities_result.get("capabilities", [])
        for capability in capabilities:
            if isinstance(capability, str) and capability == capability_name:
                return success(capability=capability_name, available=True)

            if isinstance(capability, dict):
                name = str(capability.get("name", ""))
                class_name = str(capability.get("__class", ""))
                if name == capability_name or class_name == capability_name:
                    return success(capability=capability_name, available=True)
                if name.endswith(capability_name) or class_name.endswith(capability_name):
                    return success(capability=capability_name, available=True)

        return success(capability=capability_name, available=False)

    def get_state(self) -> dict[str, Any]:
        response = self._request_json("GET", "/api/v2/robot/state")
        if not response.get("ok"):
            return response

        state = response.get("data")
        if not isinstance(state, dict):
            return error(
                "motion_request_failed",
                "Unexpected robot state payload",
                error_code="motion.request.failed",
                path="/api/v2/robot/state",
            )

        return success(state=state)

    def get_status(self) -> dict[str, Any]:
        state_result = self.get_state()
        if not state_result.get("ok"):
            return state_result

        state = state_result["state"]
        status = self.extract_status(state)
        battery = self.extract_battery(state)

        return success(
            status=status,
            battery_percent=battery,
            map_ready=isinstance(state.get("map"), dict),
        )

    def get_position(self) -> dict[str, Any]:
        state_result = self.get_state()
        if not state_result.get("ok"):
            return state_result

        state = state_result["state"]
        position = self.extract_robot_position(state)
        if position is None:
            return error(
                "motion_position_unavailable",
                "Robot position is unavailable from current map state",
                error_code=ErrorCode.MOTION_POSITION_UNAVAILABLE,
            )

        return success(**position)

    def locate(self) -> dict[str, Any]:
        return self._invoke_capability("LocateCapability", {"action": "locate"})

    def home(self) -> dict[str, Any]:
        return self._invoke_capability("BasicControlCapability", {"action": "home"})

    def goto(self, x: int, y: int, angle: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"action": "goto", "coordinates": {"x": int(x), "y": int(y)}}
        if angle is not None:
            payload["angle"] = int(angle)

        return self._invoke_capability(
            "GoToLocationCapability",
            payload,
        )

    def _invoke_capability(self, capability: str, payload: dict[str, Any]) -> dict[str, Any]:
        path = f"/api/v2/robot/capabilities/{capability}"
        response = self._request_json("PUT", path, payload)
        if not response.get("ok"):
            return response

        return success(
            capability=capability,
            action=payload.get("action"),
            response=response.get("data"),
        )

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data: bytes | None = None
        headers: dict[str, str] = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib_request.Request(url=url, method=method, data=data, headers=headers)

        try:
            with self._urlopen(request, timeout=self._timeout_sec) as response:
                status_code = getattr(response, "status", response.getcode())
                raw = response.read().decode("utf-8", errors="replace")
        except urllib_error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")[:500]
            return error(
                "motion_request_failed",
                f"HTTP {exc.code} for {path}",
                error_code="motion.request.failed",
                path=path,
                status_code=exc.code,
                details=details,
            )
        except urllib_error.URLError as exc:
            return error(
                "motion_request_failed",
                f"Failed to reach Valetudo: {exc.reason}",
                error_code="motion.request.failed",
                path=path,
            )

        parsed: Any = None
        if raw.strip():
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw.strip()

        return success(path=path, status_code=status_code, data=parsed)

    @staticmethod
    def extract_status(state: dict[str, Any]) -> str | None:
        for attribute in state.get("attributes", []):
            if not isinstance(attribute, dict):
                continue
            if attribute.get("__class") != "StatusStateAttribute":
                continue
            for key in ("value", "status", "state"):
                value = attribute.get(key)
                if value:
                    return str(value)
        return None

    @staticmethod
    def extract_battery(state: dict[str, Any]) -> int | None:
        for attribute in state.get("attributes", []):
            if not isinstance(attribute, dict):
                continue
            if attribute.get("__class") != "BatteryStateAttribute":
                continue
            for key in ("value", "level", "battery", "percentage"):
                value = attribute.get(key)
                if isinstance(value, (int, float)):
                    return int(value)
        return None

    @staticmethod
    def extract_robot_position(state: dict[str, Any]) -> dict[str, int] | None:
        entities = state.get("map", {}).get("entities", [])
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            if entity.get("__class") != "PointMapEntity":
                continue
            if entity.get("type") != "robot_position":
                continue

            points = entity.get("points")
            if not isinstance(points, list) or len(points) < 2:
                continue

            x = int(points[0])
            y = int(points[1])
            angle = int(entity.get("metaData", {}).get("angle", 0))
            return {"x": x, "y": y, "angle": angle}

        return None

    @staticmethod
    def distance_to_target(position: dict[str, int], target_x: int, target_y: int) -> float:
        return math.sqrt((position["x"] - target_x) ** 2 + (position["y"] - target_y) ** 2)
