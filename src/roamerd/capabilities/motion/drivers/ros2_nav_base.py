from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict


class MotionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    x: float | None = None
    y: float | None = None
    angle: float | None = None


class MotionStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    moving: bool = False
    docked: bool | None = None


class MotionDriver(Protocol):
    completes_synchronously: bool

    async def goto(self, x: float, y: float, angle: float | None = None) -> MotionResult: ...

    async def home(self) -> MotionResult: ...

    async def stop(self) -> None: ...

    async def status(self) -> MotionStatus: ...
