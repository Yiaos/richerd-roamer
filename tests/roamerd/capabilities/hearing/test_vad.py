import pytest

from roamerd.capabilities.hearing.drivers.silero_vad import SileroVadDriver


@pytest.mark.asyncio
async def test_silero_vad_uses_threshold() -> None:
    driver = SileroVadDriver(model=lambda pcm: 0.2, threshold=0.1)

    assert await driver.is_speech(b"pcm") is True


@pytest.mark.asyncio
async def test_silero_vad_rejects_below_threshold() -> None:
    driver = SileroVadDriver(model=lambda pcm: 0.05, threshold=0.1)

    assert await driver.is_speech(b"pcm") is False
