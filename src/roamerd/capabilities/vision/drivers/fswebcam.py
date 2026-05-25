from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from roamerd.capabilities.vision.drivers.camera_base import CaptureResult

CommandRunner = Callable[[list[str]], Awaitable[None]]


class FswebcamCameraDriver:
    def __init__(
        self,
        *,
        device: str = "/dev/video0",
        skip_frames: int = 2,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self._device = device
        self._skip_frames = skip_frames
        self._command_runner = command_runner or _run_command

    async def capture(
        self,
        output_path: Path,
        *,
        width: int | None = None,
        height: int | None = None,
    ) -> CaptureResult:
        resolution = f"{width or 1280}x{height or 720}"
        command = [
            "fswebcam",
            "--device",
            self._device,
            "--resolution",
            resolution,
            "--skip",
            str(self._skip_frames),
            str(output_path),
        ]
        await self._command_runner(command)
        return CaptureResult(
            path=output_path,
            timestamp=datetime.now(UTC),
            width=width,
            height=height,
        )


async def _run_command(command: list[str]) -> None:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(stderr.decode("utf-8", errors="replace").strip())
