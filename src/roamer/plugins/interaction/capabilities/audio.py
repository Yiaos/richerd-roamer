"""Interaction audio capability."""

from datetime import datetime
from typing import Any

# Import drivers to register them
import roamer.plugins.interaction.drivers.audio  # noqa: F401
from roamer.platform.config import get_driver_config, get_driver_name
from roamer.plugins.interaction.capabilities.base import Capability
from roamer.plugins.interaction.drivers.registry import get_driver


class AudioCapability(Capability):
    """Audio capability - record and play audio."""

    def __init__(self, config: dict[str, Any]):
        """Initialize audio capability.

        Args:
            config: Full configuration dictionary
        """
        super().__init__(config)
        driver_name = get_driver_name(config, "audio")
        driver_config = get_driver_config(config, driver_name)
        self._driver = get_driver("audio", driver_name, driver_config)

    def record(
        self,
        duration: float = 5.0,
        output: str | None = None,
    ) -> dict[str, Any]:
        """Record audio from microphone.

        Args:
            duration: Recording duration in seconds
            output: Output file path (auto-generated if None)

        Returns:
            Result dict with ok, path, duration_sec, sample_rate, channels
        """
        if output is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output = f"/tmp/roamer_rec_{timestamp}.wav"

        return self._driver.record(output, duration)

    def play(self, file: str) -> dict[str, Any]:
        """Play an audio file.

        Args:
            file: Audio file path

        Returns:
            Result dict with ok, played, duration_sec
        """
        return self._driver.play(file)
