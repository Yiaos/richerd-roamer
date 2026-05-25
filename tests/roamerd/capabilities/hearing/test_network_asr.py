import pytest

from roamerd.capabilities.hearing.drivers.network_asr import NetworkAsrDriver, normalize_asr_text


class FakeWebSocket:
    def __init__(self, response: str) -> None:
        self.response = response
        self.sent: list[bytes] = []
        self.closed = False

    async def __aenter__(self) -> "FakeWebSocket":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.closed = True

    async def send(self, data: bytes) -> None:
        self.sent.append(data)

    async def recv(self) -> str:
        return self.response


@pytest.mark.asyncio
async def test_network_asr_sends_pcm_and_normalizes_text() -> None:
    socket = FakeWebSocket(" 小乐小乐  回充电\n")

    def connect(url: str) -> FakeWebSocket:
        assert url == "ws://asr"
        return socket

    driver = NetworkAsrDriver("ws://asr", connect_factory=connect)

    assert await driver.transcribe(b"pcm") == "小乐小乐回充电"
    assert socket.sent == [b"pcm"]
    assert socket.closed is True


def test_normalize_asr_text_removes_whitespace() -> None:
    assert normalize_asr_text("  现 在 几 点 \n") == "现在几点"
