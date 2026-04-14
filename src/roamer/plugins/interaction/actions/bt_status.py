"""Bluetooth status action wrapper for interaction plugin."""

from typing import Any


class BtStatusAction:
    """Dispatch bluetooth status calls through Bluez driver."""

    def __init__(self, config: dict[str, Any]):
        from roamer.plugins.interaction.drivers.bluetooth import BluezDriver

        driver_config = config.get("bluez", {})
        self._driver = BluezDriver(driver_config)

    def run(self) -> dict[str, Any]:
        """Get bluetooth status."""
        return self._driver.status()
