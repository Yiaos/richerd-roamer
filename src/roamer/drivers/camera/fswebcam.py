"""fswebcam camera driver."""

import subprocess
from pathlib import Path
from typing import Any

from roamer.drivers.camera.base import CameraDriver
from roamer.drivers.registry import register_driver
from roamer.output import error, success


class FswebcamDriver(CameraDriver):
    """Camera driver using fswebcam."""

    def snap(self, output: str, width: int, height: int) -> dict[str, Any]:
        """Capture an image using fswebcam.

        Args:
            output: Output file path
            width: Image width
            height: Image height

        Returns:
            Result dict
        """
        device = self.config.get("device", "/dev/video0")

        cmd = [
            "fswebcam",
            "-r",
            f"{width}x{height}",
            "--no-banner",
            "-d",
            device,
            output,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=10)
        except subprocess.TimeoutExpired:
            return error("camera_capture_failed", "Camera capture timed out")
        except FileNotFoundError:
            return error("camera_capture_failed", "fswebcam not installed")

        if result.returncode != 0:
            stderr = "Unknown error"
            if result.stderr:
                stderr = result.stderr.decode("utf-8", errors="replace").strip()[:500]
            return error("camera_capture_failed", "Camera capture failed", details=stderr)

        path = Path(output)
        if not path.exists():
            return error("camera_capture_failed", "Output file not created")

        try:
            size_bytes = path.stat().st_size
        except OSError as e:
            return error("camera_capture_failed", f"Failed to inspect output file: {e}")

        return success(
            path=output,
            width=width,
            height=height,
            size_bytes=size_bytes,
        )


# Register this driver
register_driver("camera", "fswebcam", FswebcamDriver)
