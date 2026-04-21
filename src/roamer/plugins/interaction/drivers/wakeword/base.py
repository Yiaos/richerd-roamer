"""Base interface for wakeword drivers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class WakewordDriver(ABC):
    """Wakeword driver interface for converse R2 path."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    @abstractmethod
    def start(self) -> None:
        """Start wakeword detection loop/resources."""

    @abstractmethod
    def stop(self) -> None:
        """Stop wakeword detection loop/resources."""

    @abstractmethod
    def wait_hit(self, timeout: float) -> bool:
        """Wait for wakeword hit until timeout, returns True if hit."""
