"""Tests for wakeword driver skeleton."""

from roamer.plugins.interaction.drivers.wakeword.openwakeword import OpenWakewordDriver


def test_openwakeword_default_no_hit() -> None:
    driver = OpenWakewordDriver({"threshold": 0.5})
    driver.start()
    try:
        assert driver.wait_hit(timeout=0.01) is False
    finally:
        driver.stop()


def test_openwakeword_mock_hit() -> None:
    driver = OpenWakewordDriver({"mock_hit": True})
    driver.start()
    try:
        assert driver.wait_hit(timeout=0.01) is True
    finally:
        driver.stop()
