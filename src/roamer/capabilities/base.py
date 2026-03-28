"""Base classes for capabilities."""

from abc import ABC
from typing import Any


class Capability(ABC):
    """Base class for all capabilities."""

    def __init__(self, config: dict[str, Any]):
        """Initialize capability with configuration.

        Args:
            config: Full configuration dictionary
        """
        self.config = config
