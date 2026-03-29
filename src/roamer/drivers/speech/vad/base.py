"""Base class for VAD drivers."""

from abc import ABC, abstractmethod
from typing import Any

import numpy as np


class VADDriver(ABC):
    """Abstract base class for VAD drivers."""

    def __init__(self, config: dict[str, Any]):
        """Initialize driver with configuration.

        Args:
            config: Driver-specific configuration
        """
        self.config = config

    @abstractmethod
    def detect(
        self, audio: np.ndarray, sample_rate: int, debug: bool = False
    ) -> dict[str, Any]:
        """Detect speech segments in audio.

        Args:
            audio: Audio samples as numpy array
            sample_rate: Sample rate in Hz
            debug: Enable debug logging

        Returns:
            Result dict with speech_detected, segments list
        """
        pass
