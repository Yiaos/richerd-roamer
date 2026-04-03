"""Base class for TTS drivers."""

from abc import ABC, abstractmethod
from typing import Any


class TTSDriver(ABC):
    """Abstract base class for TTS drivers."""

    def __init__(self, config: dict[str, Any]):
        """Initialize driver with configuration.

        Args:
            config: Driver-specific configuration
        """
        self.config = config

    @abstractmethod
    def synthesize(self, text: str, output: str, style: str | None = None) -> dict[str, Any]:
        """Synthesize speech from text.

        Args:
            text: Text to synthesize
            output: Output audio file path
            style: Optional emotional expression style

        Returns:
            Result dict with ok, path, duration_sec
        """
        pass
