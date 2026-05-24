import asyncio
import tempfile
from pathlib import Path

import pytest

from roamerd.bridges.control.commands import StaticRouter
from roamerd.bridges.control.ipc import ControlClient
from roamerd.bridges.control.protocol import RequestEnvelope
from roamerd.bridges.control.server import ControlBridgeServer


@pytest.mark.asyncio
async def test_control_bridge_server_roundtrip_and_socket_permissions() -> None:
    socket_dir = Path(tempfile.mkdtemp(prefix="roamerd-", dir="/tmp"))
    socket_path = socket_dir / "roamer.sock"
    server = ControlBridgeServer(socket_path=socket_path, router=StaticRouter({"pong": True}))
    await server.start()
    try:
        client = ControlClient(socket_path)
        response = await client.request(RequestEnvelope(request_id="req-1", op="ping"))
    finally:
        await server.stop()

    assert response.result == {"pong": True}
    assert oct(socket_path.stat().st_mode & 0o777) == "0o600"


@pytest.mark.asyncio
async def test_control_bridge_refuses_to_unlink_active_socket() -> None:
    socket_dir = Path(tempfile.mkdtemp(prefix="roamerd-", dir="/tmp"))
    socket_path = socket_dir / "roamer.sock"
    first = ControlBridgeServer(socket_path=socket_path, router=StaticRouter({"pong": True}))
    second = ControlBridgeServer(socket_path=socket_path, router=StaticRouter({"pong": True}))

    await first.start()
    try:
        with pytest.raises(RuntimeError, match="active control socket"):
            await second.start()
    finally:
        await first.stop()


@pytest.mark.asyncio
async def test_control_bridge_refuses_to_unlink_active_non_protocol_socket() -> None:
    socket_dir = Path(tempfile.mkdtemp(prefix="roamerd-", dir="/tmp"))
    socket_path = socket_dir / "roamer.sock"
    silent_server = await asyncio.start_unix_server(
        lambda _reader, _writer: None,
        path=str(socket_path),
    )
    server = ControlBridgeServer(socket_path=socket_path, router=StaticRouter({"pong": True}))

    try:
        with pytest.raises(RuntimeError, match="active control socket"):
            await server.start()
    finally:
        silent_server.close()
        await silent_server.wait_closed()
