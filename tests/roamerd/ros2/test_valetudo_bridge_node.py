import json
import sys
from pathlib import Path
from urllib import error as urllib_error

ROS_PACKAGE = Path(__file__).resolve().parents[3] / "ros2_ws" / "src" / "roamer_ros"
sys.path.insert(0, str(ROS_PACKAGE))

from roamer_ros.valetudo_bridge_node import (  # noqa: E402
    ValetudoClient,
    distance_to_target,
    extract_battery,
    extract_robot_position,
    extract_status,
    handle_motion_command,
)


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def getcode(self):
        return self.status

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def _state():
    return {
        "attributes": [
            {"__class": "StatusStateAttribute", "value": "idle"},
            {"__class": "BatteryStateAttribute", "value": 87},
        ],
        "map": {
            "entities": [
                {
                    "__class": "PointMapEntity",
                    "type": "robot_position",
                    "points": [10, 20],
                    "metaData": {"angle": 90},
                }
            ]
        },
    }


def test_valetudo_state_extractors() -> None:
    state = _state()
    assert extract_status(state) == "idle"
    assert extract_battery(state) == 87
    assert extract_robot_position(state) == {"x": 10, "y": 20, "angle": 90}
    assert distance_to_target({"x": 10, "y": 20}, 13, 24) == 5.0


def test_valetudo_client_status_and_goto() -> None:
    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request.method, request.full_url, request.data))
        if request.full_url.endswith("/state"):
            return FakeResponse(_state())
        return FakeResponse({"accepted": True})

    client = ValetudoClient(host="robot.local", port=80, urlopen=fake_urlopen)
    assert client.get_status()["battery_percent"] == 87
    assert client.goto(x=1, y=2, angle=3)["ok"] is True
    assert requests[-1][0] == "PUT"
    assert requests[-1][1].endswith("/api/v2/robot/capabilities/GoToLocationCapability")


def test_valetudo_client_http_error() -> None:
    def fake_urlopen(request, timeout):
        raise urllib_error.URLError("offline")

    client = ValetudoClient(host="robot.local", urlopen=fake_urlopen)
    result = client.get_state()
    assert result["ok"] is False
    assert result["error_code"] == "motion.request.failed"


def test_valetudo_bridge_handles_json_motion_commands() -> None:
    calls = []

    class FakeClient:
        def goto(self, *, x, y, angle=None):
            calls.append(("goto", x, y, angle))
            return {"ok": True, "accepted": True}

        def home(self):
            calls.append(("home",))
            return {"ok": True}

        def stop(self):
            calls.append(("stop",))
            return {"ok": True}

        def get_position(self):
            return {"ok": True, "x": 1, "y": 2, "angle": 3}

        def get_status(self):
            return {"ok": True, "battery_percent": 87}

    response = handle_motion_command(
        {
            "op": "goto",
            "correlation_id": "corr-1",
            "target": {"x": 10, "y": 20, "angle": 90},
        },
        client=FakeClient(),
    )

    assert response["ok"] is True
    assert response["correlation_id"] == "corr-1"
    assert calls == [("goto", 10, 20, 90)]
