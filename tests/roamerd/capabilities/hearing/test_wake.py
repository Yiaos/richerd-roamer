import asyncio

import pytest

from roamerd.capabilities.hearing.drivers.openwakeword import OpenWakewordDriver
from roamerd.capabilities.hearing.drivers.su03t_gpio import Su03tGpioWakewordDriver
from roamerd.capabilities.hearing.drivers.wakeword_base import WakeEvent


@pytest.mark.asyncio
async def test_su03t_gpio_driver_debounces_min_interval() -> None:
    events: asyncio.Queue[None] = asyncio.Queue()
    now = 100.0

    async def wait_edge() -> None:
        await events.get()

    def clock() -> float:
        return now

    driver = Su03tGpioWakewordDriver(
        wait_edge=wait_edge,
        clock=clock,
        min_interval_sec=1.0,
        wakeword="小乐小乐",
    )

    await events.put(None)
    first = await driver.wait_for_wake()
    await events.put(None)
    now = 100.2
    ignored = asyncio.create_task(driver.wait_for_wake())
    await asyncio.sleep(0)
    assert not ignored.done()

    now = 101.2
    await events.put(None)
    second = await ignored

    assert first == WakeEvent(wakeword="小乐小乐", confidence=1.0)
    assert second.wakeword == "小乐小乐"


@pytest.mark.asyncio
async def test_openwakeword_driver_wraps_detector() -> None:
    async def detector() -> tuple[str, float]:
        return ("小乐", 0.91)

    driver = OpenWakewordDriver(detector=detector)

    assert await driver.wait_for_wake() == WakeEvent(wakeword="小乐", confidence=0.91)
