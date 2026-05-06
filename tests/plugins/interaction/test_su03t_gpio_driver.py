"""Tests for SU-03T GPIO wakeword driver."""

from roamer.plugins.interaction.drivers.wakeword.su03t_gpio import Su03tGpioDriver


class FakeRequest:
    def __init__(self, events):
        self.events = list(events)
        self.released = False
        self.wait_timeouts = []

    def wait_edge_events(self, timeout):
        self.wait_timeouts.append(timeout)
        return bool(self.events)

    def read_edge_events(self):
        if not self.events:
            return []
        return [self.events.pop(0)]

    def release(self):
        self.released = True


def test_su03t_gpio_timeout_without_event() -> None:
    request = FakeRequest([])
    driver = Su03tGpioDriver({"request_factory": lambda cfg: request})
    driver.start()
    try:
        assert driver.wait_hit(timeout=0.01) is False
    finally:
        driver.stop()

    assert request.released is True


def test_su03t_gpio_hit_with_fake_event() -> None:
    request = FakeRequest([object()])
    driver = Su03tGpioDriver({"request_factory": lambda cfg: request})
    driver.start()
    try:
        assert driver.wait_hit(timeout=0.01) is True
    finally:
        driver.stop()


def test_su03t_gpio_allows_blocking_wait_without_timeout() -> None:
    request = FakeRequest([object()])
    driver = Su03tGpioDriver({"request_factory": lambda cfg: request})
    driver.start()
    try:
        assert driver.wait_hit(timeout=None) is True
    finally:
        driver.stop()

    assert request.wait_timeouts == [None]


def test_su03t_gpio_ignores_second_event_inside_min_interval() -> None:
    request = FakeRequest([object(), object()])
    now = [100.0]

    driver = Su03tGpioDriver(
        {
            "request_factory": lambda cfg: request,
            "min_interval_sec": 1.5,
            "clock": lambda: now[0],
        }
    )
    driver.start()
    try:
        assert driver.wait_hit(timeout=0.01) is True
        now[0] = 100.5
        assert driver.wait_hit(timeout=0.01) is False
    finally:
        driver.stop()
