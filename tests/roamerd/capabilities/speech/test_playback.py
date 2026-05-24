from pathlib import Path

import pytest

from roamerd.capabilities.speech.drivers.alsa_playback import AlsaPlaybackDriver
from roamerd.capabilities.speech.playback import BluetoothPlaybackDriver
from roamerd.capabilities.speech.playback_state import PlaybackState


@pytest.mark.asyncio
async def test_alsa_playback_invokes_aplay(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    async def runner(command: list[str], timeout_sec: float) -> None:
        calls.append(command)
        assert timeout_sec == 30.0

    path = tmp_path / "out.wav"
    path.write_bytes(b"wav")
    driver = AlsaPlaybackDriver(device="hw:1,0", command_runner=runner)

    await driver.play(path)

    assert calls == [["aplay", "-q", "-D", "hw:1,0", str(path)]]


@pytest.mark.asyncio
async def test_bluetooth_playback_reconnects_before_play(tmp_path: Path) -> None:
    class Bluetooth:
        connected = False

        async def status(self) -> str:
            return "connected" if self.connected else "disconnected"

        async def connect(self) -> None:
            self.connected = True

        async def disconnect(self) -> None:
            self.connected = False

    class Playback:
        played: list[Path] = []

        async def play(self, path: Path) -> None:
            self.played.append(path)

    path = tmp_path / "out.wav"
    bluetooth = Bluetooth()
    playback = Playback()

    await BluetoothPlaybackDriver(playback, bluetooth).play(path)

    assert bluetooth.connected is True
    assert playback.played == [path]


def test_playback_state_tracks_generation_and_staleness() -> None:
    state = PlaybackState(stale_after_sec=0.01)

    first = state.started(now=10.0)
    assert state.active is True
    assert state.stale(now=10.005) is False
    assert state.stale(now=10.02) is True

    second = state.finished()
    assert second > first
    assert state.active is False
