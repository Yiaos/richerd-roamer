from __future__ import annotations

from typing import Protocol


class BluetoothDriver(Protocol):
    async def status(self) -> str: ...

    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...
