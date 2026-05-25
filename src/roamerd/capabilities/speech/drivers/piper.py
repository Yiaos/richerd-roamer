from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from roamerd.capabilities.speech.drivers.tts_base import SynthResult

CommandRunner = Callable[[list[str], str, float], Awaitable[None]]


class PiperTtsDriver:
    def __init__(
        self,
        *,
        binary: str,
        model: str,
        timeout_sec: float = 20.0,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self._binary = binary
        self._model = model
        self._timeout_sec = timeout_sec
        self._command_runner = command_runner or _run_command

    async def synthesize(self, text: str, output_path: Path) -> SynthResult:
        command = [self._binary, "--model", self._model, "--output_file", str(output_path)]
        await self._command_runner(command, text, self._timeout_sec)
        return SynthResult(path=output_path)


async def _run_command(command: list[str], input_text: str, timeout_sec: float) -> None:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(
            process.communicate(input_text.encode("utf-8")),
            timeout=timeout_sec,
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise TimeoutError("piper timed out") from None
    if process.returncode != 0:
        raise RuntimeError(stderr.decode("utf-8", errors="replace").strip())
