"""Camera capability."""

from datetime import datetime
from typing import Any

# Import drivers to register them
import roamer.drivers.camera  # noqa: F401
from roamer.capabilities.base import Capability
from roamer.config import get_driver_config, get_driver_name
from roamer.drivers.registry import get_driver


class CameraCapability(Capability):
    """Camera capability - capture images."""

    def __init__(self, config: dict[str, Any]):
        """Initialize camera capability.

        Args:
            config: Full configuration dictionary
        """
        super().__init__(config)
        driver_name = get_driver_name(config, "camera")
        driver_config = get_driver_config(config, driver_name)
        self._driver = get_driver("camera", driver_name, driver_config)

    def snap(
        self,
        output: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> dict[str, Any]:
        """Capture an image.

        Args:
            output: Output file path (auto-generated if None)
            width: Image width (uses config default if None)
            height: Image height (uses config default if None)

        Returns:
            Result dict with ok, path, width, height, size_bytes
        """
        driver_name = get_driver_name(self.config, "camera")
        driver_config = get_driver_config(self.config, driver_name)

        if output is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output = f"/tmp/roamer_snap_{timestamp}.jpg"

        if width is None:
            width = driver_config.get("width", 1280)
        if height is None:
            height = driver_config.get("height", 720)

        return self._driver.snap(output, width, height)
