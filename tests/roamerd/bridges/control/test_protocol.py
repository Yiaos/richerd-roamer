import pytest

from roamerd.bridges.control.protocol import (
    ProtocolError,
    RequestEnvelope,
    ResponseEnvelope,
    decode_request_line,
    encode_response,
)


def test_node_protocol_v1_roundtrip() -> None:
    request = RequestEnvelope(
        request_id="req-1",
        op="ping",
        client="test",
        source="cli",
        args={"verbose": True},
    )
    response = ResponseEnvelope(
        request_id=request.request_id,
        trace_id=request.trace_id,
        op=request.op,
        status="ok",
        result={"pong": True},
    )

    decoded = decode_request_line(request.model_dump_json().encode() + b"\n")
    encoded = encode_response(response)

    assert decoded == request
    assert encoded.endswith(b"\n")
    assert ResponseEnvelope.model_validate_json(encoded).result == {"pong": True}


def test_protocol_rejects_malformed_and_oversized_messages() -> None:
    with pytest.raises(ProtocolError):
        decode_request_line(b"{bad json}\n")
    with pytest.raises(ProtocolError):
        decode_request_line(b"{}" * 1024, max_bytes=10)
