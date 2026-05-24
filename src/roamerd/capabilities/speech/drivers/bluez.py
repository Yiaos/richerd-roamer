from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

CommandRunner = Callable[[list[str], float], Awaitable[str]]


class BluezBluetoothDriver:
    def __init__(
        self,
        speaker_mac: str,
        *,
        timeout_sec: float = 20.0,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self._speaker_mac = speaker_mac
        self._timeout_sec = timeout_sec
        self._command_runner = command_runner or _run_command

    async def status(self) -> str:
        output = await self._command_runner(
            ["bluetoothctl", "info", self._speaker_mac],
            self._timeout_sec,
        )
        return "connected" if parse_connected(output) else "disconnected"

    async def connect(self) -> None:
        await self._command_runner(
            ["bluetoothctl", "connect", self._speaker_mac],
            self._timeout_sec,
        )

    async def disconnect(self) -> None:
        await self._command_runner(
            ["bluetoothctl", "disconnect", self._speaker_mac],
            self._timeout_sec,
        )


def parse_connected(output: str) -> bool:
    return any(line.strip().lower() == "connected: yes" for line in output.splitlines())


async def _run_command(command: list[str], timeout_sec: float) -> str:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_sec)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise TimeoutError(f"{command[0]} timed out") from None
    if process.returncode != 0:
        raise RuntimeError(stderr.decode("utf-8", errors="replace").strip())
    return stdout.decode("utf-8", errors="replace")
