from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from roamerd.capabilities.speech.drivers.tts_base import SynthResult

CommandRunner = Callable[[list[str], float], Awaitable[None]]


class EdgeTtsDriver:
    def __init__(
        self,
        *,
        voice: str,
        timeout_sec: float = 20.0,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self._voice = voice
        self._timeout_sec = timeout_sec
        self._command_runner = command_runner or _run_command

    async def synthesize(self, text: str, output_path: Path) -> SynthResult:
        command = [
            "edge-tts",
            "--voice",
            self._voice,
            "--text",
            text,
            "--write-media",
            str(output_path),
        ]
        await self._command_runner(command, self._timeout_sec)
        return SynthResult(path=output_path)


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
        raise TimeoutError("edge-tts timed out") from None
    if process.returncode != 0:
        raise RuntimeError(stderr.decode("utf-8", errors="replace").strip())
