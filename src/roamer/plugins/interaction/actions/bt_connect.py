"""Bluetooth connect action wrapper for interaction plugin."""

from typing import Any


class BtConnectAction:
    """Dispatch bluetooth connect calls through Bluez driver."""

    def __init__(self, config: dict[str, Any]):
        from roamer.plugins.interaction.drivers.bluetooth import BluezDriver

        driver_config = config.get("bluez", {})
        self._driver = BluezDriver(driver_config)

    def run(self, address: str) -> dict[str, Any]:
        """Connect a bluetooth device."""
        return self._driver.connect(address)
