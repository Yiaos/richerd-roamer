"""Base class for audio drivers."""

from abc import ABC, abstractmethod
from typing import Any


class AudioDriver(ABC):
    """Abstract base class for audio drivers."""

    def __init__(self, config: dict[str, Any]):
        """Initialize driver with configuration.

        Args:
            config: Driver-specific configuration
        """
        self.config = config

    @abstractmethod
    def record(self, output: str, duration: float) -> dict[str, Any]:
        """Record audio.

        Args:
            output: Output file path
            duration: Recording duration in seconds

        Returns:
            Result dict with ok, path, duration_sec, sample_rate, channels
        """
        pass

    @abstractmethod
    def play(self, file: str) -> dict[str, Any]:
        """Play audio file.

        Args:
            file: Audio file path

        Returns:
            Result dict with ok, played, duration_sec
        """
        pass
