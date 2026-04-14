"""Base class for ASR drivers."""

from abc import ABC, abstractmethod
from typing import Any


class ASRDriver(ABC):
    """Abstract base class for ASR drivers."""

    def __init__(self, config: dict[str, Any]):
        """Initialize driver with configuration.

        Args:
            config: Driver-specific configuration
        """
        self.config = config

    @abstractmethod
    def transcribe(self, audio_path: str) -> dict[str, Any]:
        """Transcribe speech from audio file.

        Args:
            audio_path: Path to audio file

        Returns:
            Result dict with text, confidence
        """
        pass
