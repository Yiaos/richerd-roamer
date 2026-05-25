import json
from pathlib import Path

from roamerd.bridges.control.protocol import RequestEnvelope, ResponseEnvelope

FIXTURE_DIR = Path(__file__).parent


def test_control_request_fixture_matches_node_protocol_v1() -> None:
    payload = json.loads((FIXTURE_DIR / "control_request_ping.json").read_text())

    request = RequestEnvelope.model_validate(payload)

    assert request.request_id == "req-1"
    assert request.trace_id == "trace-1"
    assert request.authority == "socket"


def test_control_response_fixture_echoes_correlation_fields() -> None:
    payload = json.loads((FIXTURE_DIR / "control_response_ping.json").read_text())

    response = ResponseEnvelope.model_validate(payload)

    assert response.request_id == "req-1"
    assert response.trace_id == "trace-1"
    assert response.result == {"pong": True}
