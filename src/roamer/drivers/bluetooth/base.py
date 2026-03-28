"""Base class for Bluetooth drivers."""

from abc import ABC, abstractmethod
from typing import Any


class BluetoothDriver(ABC):
    """Abstract base class for Bluetooth drivers."""

    def __init__(self, config: dict[str, Any]):
        """Initialize driver with configuration.

        Args:
            config: Driver-specific configuration
        """
        self.config = config

    @abstractmethod
    def status(self) -> dict[str, Any]:
        """Get Bluetooth status.

        Returns:
            Result dict with controller info and connected devices
        """
        pass

    @abstractmethod
    def connect(self, address: str) -> dict[str, Any]:
        """Connect to a Bluetooth device.

        Args:
            address: Device address or name

        Returns:
            Result dict
        """
        pass

    @abstractmethod
    def disconnect(self, address: str) -> dict[str, Any]:
        """Disconnect from a Bluetooth device.

        Args:
            address: Device address

        Returns:
            Result dict
        """
        pass
