"""Tests for Valetudo motion driver behavior."""

from __future__ import annotations

import json
from urllib import error as urllib_error

from roamer.plugins.motion.drivers.valetudo import ValetudoMotionDriver


class _FakeResponse:
    def __init__(self, status: int, payload):
        self.status = status
        self._payload = payload

    def read(self) -> bytes:
        if isinstance(self._payload, str):
            return self._payload.encode("utf-8")
        return json.dumps(self._payload).encode("utf-8")

    def getcode(self) -> int:
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _urlopen_factory(responses):
    state = {"i": 0}

    def _urlopen(request, timeout=0):
        idx = state["i"]
        state["i"] += 1
        resp = responses[idx]
        if isinstance(resp, Exception):
            raise resp
        return _FakeResponse(200, resp)

    return _urlopen


def _state(status: str = "idle", battery: int = 77, x: int = 10, y: int = 20, angle: int = 90):
    return {
        "attributes": [
            {"__class": "StatusStateAttribute", "value": status},
            {"__class": "BatteryStateAttribute", "value": battery},
        ],
        "map": {
            "entities": [
                {
                    "__class": "PointMapEntity",
                    "type": "robot_position",
                    "points": [x, y],
                    "metaData": {"angle": angle},
                }
            ]
        },
    }


def _cfg() -> dict:
    return {"host": "10.0.0.100", "port": 80, "timeout_sec": 8.0}


def test_get_status_parses_state_fields() -> None:
    driver = ValetudoMotionDriver(
        _cfg(),
        urlopen=_urlopen_factory([_state(status="docked", battery=91)]),
    )

    result = driver.get_status()

    assert result["ok"] is True
    assert result["status"] == "docked"
    assert result["battery_percent"] == 91
    assert result["map_ready"] is True


def test_get_position_returns_robot_position() -> None:
    driver = ValetudoMotionDriver(
        _cfg(),
        urlopen=_urlopen_factory([_state(x=2076, y=2378, angle=277)]),
    )

    result = driver.get_position()

    assert result["ok"] is True
    assert result["x"] == 2076
    assert result["y"] == 2378
    assert result["angle"] == 277


def test_get_position_returns_unavailable_error_when_missing() -> None:
    driver = ValetudoMotionDriver(
        _cfg(),
        urlopen=_urlopen_factory([
            {
                "attributes": [{"__class": "StatusStateAttribute", "value": "idle"}],
                "map": {"entities": []},
            }
        ]),
    )

    result = driver.get_position()

    assert result["ok"] is False
    assert result["error_code"] == "motion.position.unavailable"


def test_home_invokes_basic_control_capability() -> None:
    driver = ValetudoMotionDriver(_cfg(), urlopen=_urlopen_factory([{"accepted": True}]))

    result = driver.home()

    assert result["ok"] is True
    assert result["capability"] == "BasicControlCapability"
    assert result["action"] == "home"


def test_goto_invokes_goto_capability() -> None:
    driver = ValetudoMotionDriver(_cfg(), urlopen=_urlopen_factory([{"accepted": True}]))

    result = driver.goto(25500, 25300)

    assert result["ok"] is True
    assert result["capability"] == "GoToLocationCapability"
    assert result["action"] == "goto"


def test_has_capability_true_and_false() -> None:
    caps = [
        "LocateCapability",
        {"name": "GoToLocationCapability"},
    ]
    driver = ValetudoMotionDriver(_cfg(), urlopen=_urlopen_factory([caps, caps]))

    assert driver.has_capability("GoToLocationCapability")["available"] is True
    assert driver.has_capability("BasicControlCapability")["available"] is False


def test_request_json_handles_url_error() -> None:
    driver = ValetudoMotionDriver(
        _cfg(),
        urlopen=_urlopen_factory([urllib_error.URLError("network down")]),
    )

    result = driver.get_status()

    assert result["ok"] is False
    assert result["error"] == "motion_request_failed"
    assert result["error_code"] == "motion.request.failed"


def test_init_requires_host_and_port() -> None:
    try:
        ValetudoMotionDriver({})
        assert False, "Expected ValueError when host/port missing"
    except ValueError as exc:
        assert str(exc) == "valetudo.host is required"

    try:
        ValetudoMotionDriver({"host": "10.0.0.100"})
        assert False, "Expected ValueError when port missing"
    except ValueError as exc:
        assert str(exc) == "valetudo.port is required"


def test_init_rejects_invalid_port() -> None:
    try:
        ValetudoMotionDriver({"host": "10.0.0.100", "port": "abc"})
        assert False, "Expected ValueError for non-integer port"
    except ValueError as exc:
        assert str(exc) == "valetudo.port must be an integer"

    try:
        ValetudoMotionDriver({"host": "10.0.0.100", "port": 0})
        assert False, "Expected ValueError for non-positive port"
    except ValueError as exc:
        assert str(exc) == "valetudo.port must be > 0"


def test_distance_to_target() -> None:
    dist = ValetudoMotionDriver.distance_to_target({"x": 0, "y": 0}, 3, 4)
    assert round(dist, 2) == 5.0
