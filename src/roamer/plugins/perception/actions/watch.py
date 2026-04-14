"""Watch action for perception plugin."""

from datetime import datetime
from typing import Any

from roamer.plugins.perception.drivers.camera_fswebcam import FswebcamDriver


class WatchAction:
    """Capture an image through the perception camera driver."""

    def __init__(self, config: dict[str, Any], driver: FswebcamDriver | None = None):
        """Initialize watch action with config and optional injected driver."""
        self._config = config
        driver_config = config.get("fswebcam", {})
        self._driver = driver or FswebcamDriver(driver_config)

    def run(
        self,
        output: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> dict[str, Any]:
        """Capture an image, filling defaults from config when omitted."""
        driver_config = self._config.get("fswebcam", {})

        if output is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output = f"/tmp/roamer_snap_{timestamp}.jpg"

        if width is None:
            width = int(driver_config.get("width", 1280))
        if height is None:
            height = int(driver_config.get("height", 720))

        return self._driver.snap(output, width, height)
