"""Bluetooth capability."""

from typing import Any

# Import drivers to register them
import roamer.drivers.bluetooth  # noqa: F401
from roamer.capabilities.base import Capability
from roamer.config import get_driver_config, get_driver_name
from roamer.drivers.registry import get_driver


class BluetoothCapability(Capability):
    """Bluetooth capability - manage Bluetooth devices."""

    def __init__(self, config: dict[str, Any]):
        """Initialize Bluetooth capability.

        Args:
            config: Full configuration dictionary
        """
        super().__init__(config)
        driver_name = get_driver_name(config, "bluetooth")
        driver_config = get_driver_config(config, driver_name)
        self._driver = get_driver("bluetooth", driver_name, driver_config)

    def status(self) -> dict[str, Any]:
        """Get Bluetooth status.

        Returns:
            Result dict with controller info and connected devices
        """
        return self._driver.status()

    def connect(self, address: str) -> dict[str, Any]:
        """Connect to a Bluetooth device.

        Args:
            address: Device address or name

        Returns:
            Result dict
        """
        return self._driver.connect(address)

    def disconnect(self, address: str) -> dict[str, Any]:
        """Disconnect from a Bluetooth device.

        Args:
            address: Device address

        Returns:
            Result dict
        """
        return self._driver.disconnect(address)
