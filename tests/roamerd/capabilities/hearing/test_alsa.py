import pytest

from roamerd.capabilities.hearing.drivers.alsa_capture import AlsaCaptureDriver


@pytest.mark.asyncio
async def test_alsa_capture_runs_arecord_and_returns_pcm() -> None:
    calls: list[list[str]] = []

    async def runner(command: list[str], timeout_sec: float) -> bytes:
        calls.append(command)
        assert timeout_sec == 2.0
        return b"pcm"

    driver = AlsaCaptureDriver(
        device="hw:1,0",
        sample_rate=16000,
        channels=1,
        duration_sec=2.0,
        command_runner=runner,
    )

    assert await driver.record() == b"pcm"
    assert calls == [
        [
            "arecord",
            "-q",
            "-D",
            "hw:1,0",
            "-r",
            "16000",
            "-c",
            "1",
            "-f",
            "S16_LE",
            "-d",
            "2",
            "-t",
            "raw",
        ]
    ]


@pytest.mark.asyncio
async def test_alsa_capture_surfaces_command_failure() -> None:
    async def runner(command: list[str], timeout_sec: float) -> bytes:
        raise RuntimeError("device busy")

    driver = AlsaCaptureDriver(command_runner=runner)

    with pytest.raises(RuntimeError, match="device busy"):
        await driver.record()
