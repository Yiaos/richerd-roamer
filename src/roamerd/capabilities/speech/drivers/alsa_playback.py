from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

CommandRunner = Callable[[list[str], float], Awaitable[None]]


class AlsaPlaybackDriver:
    def __init__(
        self,
        *,
        device: str = "default",
        timeout_sec: float = 30.0,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self._device = device
        self._timeout_sec = timeout_sec
        self._command_runner = command_runner or _run_command

    async def play(self, path: Path) -> None:
        await self._command_runner(
            ["aplay", "-q", "-D", self._device, str(path)],
            self._timeout_sec,
        )


async def _run_command(command: list[str], timeout_sec: float) -> None:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_sec)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise TimeoutError("aplay timed out") from None
    if process.returncode != 0:
        raise RuntimeError(stderr.decode("utf-8", errors="replace").strip())
