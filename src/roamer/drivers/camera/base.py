"""Base class for camera drivers."""

from abc import ABC, abstractmethod
from typing import Any


class CameraDriver(ABC):
    """Abstract base class for camera drivers."""

    def __init__(self, config: dict[str, Any]):
        """Initialize driver with configuration.

        Args:
            config: Driver-specific configuration
        """
        self.config = config

    @abstractmethod
    def snap(self, output: str, width: int, height: int) -> dict[str, Any]:
        """Capture an image.

        Args:
            output: Output file path
            width: Image width
            height: Image height

        Returns:
            Result dict with ok, path, width, height, size_bytes
        """
        pass
