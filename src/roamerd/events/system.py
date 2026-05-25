from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict


class Startup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["system.startup"]] = "system.startup"

    session_id: str


class ShutdownRequested(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["system.shutdown_requested"]] = "system.shutdown_requested"

    reason: str


class Shutdown(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["system.shutdown"]] = "system.shutdown"

    reason: str


class ModuleReady(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["system.module_ready"]] = "system.module_ready"

    module: str


class HealthChanged(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["system.health_changed"]] = "system.health_changed"

    component: str
    status: str
    kind: str | None = None


class HandlerTimeout(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["system.handler_timeout"]] = "system.handler_timeout"

    event_type: str
    handler: str
    timeout_sec: float


class QueueOverflow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["system.queue_overflow"]] = "system.queue_overflow"

    priority: str
    dropped_event_type: str


class WatchdogTriggered(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENT_TYPE: ClassVar[Literal["system.watchdog_triggered"]] = "system.watchdog_triggered"

    stalled_for_sec: float
