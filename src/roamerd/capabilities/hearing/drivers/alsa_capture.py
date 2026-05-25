from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

CommandRunner = Callable[[list[str], float], Awaitable[bytes]]


class AlsaCaptureDriver:
    def __init__(
        self,
        *,
        device: str = "default",
        sample_rate: int = 16000,
        channels: int = 1,
        duration_sec: float = 3.0,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self._device = device
        self._sample_rate = sample_rate
        self._channels = channels
        self._duration_sec = duration_sec
        self._command_runner = command_runner or _run_capture_command

    async def record(self) -> bytes:
        command = [
            "arecord",
            "-q",
            "-D",
            self._device,
            "-r",
            str(self._sample_rate),
            "-c",
            str(self._channels),
            "-f",
            "S16_LE",
            "-d",
            str(int(self._duration_sec)),
            "-t",
            "raw",
        ]
        return await self._command_runner(command, self._duration_sec)


async def _run_capture_command(command: list[str], timeout_sec: float) -> bytes:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_sec + 1.0,
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise TimeoutError("arecord timed out") from None
    if process.returncode != 0:
        raise RuntimeError(stderr.decode("utf-8", errors="replace").strip())
    return stdout
