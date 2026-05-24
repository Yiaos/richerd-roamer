from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from roamerd.bridges.base import Bridge
from roamerd.capabilities.base import CapabilityModule
from roamerd.events import Event
from roamerd.kernel.event_bus import EventBus
from roamerd.types import JSONDict


class Supervisor:
    def __init__(
        self,
        bus: EventBus,
        *,
        health_interval_sec: float = 30.0,
        stop_timeout_sec: float = 5.0,
    ) -> None:
        self._bus = bus
        self._modules: list[CapabilityModule] = []
        self._bridges: list[Bridge] = []
        self._health_interval_sec = health_interval_sec
        self._stop_timeout_sec = stop_timeout_sec
        self._health_task: asyncio.Task[None] | None = None
        self._last_health: dict[str, str] = {}

    def register_module(self, module: CapabilityModule) -> None:
        self._modules.append(module)

    def register_bridge(self, bridge: Bridge) -> None:
        self._bridges.append(bridge)

    @property
    def modules(self) -> tuple[CapabilityModule, ...]:
        return tuple(self._modules)

    @property
    def bridges(self) -> tuple[Bridge, ...]:
        return tuple(self._bridges)

    async def start(self) -> None:
        for module in self._modules:
            await module.start(self._bus)
            await self._publish_ready(module.name)
        for bridge in self._bridges:
            await bridge.start(self._bus)
            await self._publish_ready(bridge.name)
        self._health_task = asyncio.create_task(self._health_loop())

    async def stop(self) -> None:
        if self._health_task is not None:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None
        for bridge in reversed(self._bridges):
            await asyncio.wait_for(bridge.stop(), timeout=self._stop_timeout_sec)
        for module in reversed(self._modules):
            await asyncio.wait_for(module.stop(), timeout=self._stop_timeout_sec)

    async def _publish_ready(self, name: str) -> None:
        await self._bus.publish(
            Event(
                event_type="system.module_ready",
                source="supervisor",
                session_id="supervisor",
                payload={"module": name},
            )
        )

    async def _health_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._health_interval_sec)
                await self._check_all_health()
        except asyncio.CancelledError:
            return

    async def _check_all_health(self) -> None:
        for module in self._modules:
            await self._check_component(module.name, module.health_check)
        for bridge in self._bridges:
            await self._check_component(bridge.name, bridge.health_check, kind="bridge")

    async def _check_component(
        self,
        name: str,
        health_check: Callable[[], Awaitable[str]],
        *,
        kind: str = "module",
    ) -> None:
        try:
            status = await health_check()
        except Exception:
            status = "unavailable"
        if self._last_health.get(name) == status:
            return
        self._last_health[name] = status
        payload: JSONDict = {"component": name, "status": status}
        if kind == "bridge":
            payload["kind"] = "bridge"
        await self._bus.publish(
            Event(
                event_type="system.health_changed",
                source="supervisor",
                session_id="supervisor",
                payload=payload,
            )
        )
