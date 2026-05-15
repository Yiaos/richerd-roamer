"""Lifecycle owner for modules and bridges."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Iterable
from contextlib import suppress
from typing import Protocol, runtime_checkable

from roamerd.bridges.base import Bridge
from roamerd.bridges.control.unix_socket import request_via_socket
from roamerd.capabilities.base import CapabilityModule
from roamerd.config.schema import StartupConfig
from roamerd.events.base import make_event
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.state_manager import HealthState


@runtime_checkable
class BluetoothStartupConnector(Protocol):
    async def ensure_connected(self) -> bool: ...

    async def health_check(self) -> HealthState: ...


@runtime_checkable
class StartupRunner(Protocol):
    async def run_proxy_init(self, script: str, timeout_sec: float) -> None: ...

    async def connect_speaker(
        self,
        *,
        controller_ready_timeout_sec: float,
        connect_retry_timeout_sec: float,
        retry_interval_sec: float,
    ) -> None: ...

    async def ensure_control_bridge(self, *, timeout_sec: float) -> None: ...


class SubprocessStartupRunner:
    def __init__(
        self,
        *,
        bluetooth_driver: BluetoothStartupConnector | None = None,
        control_socket_path: str | None = None,
    ) -> None:
        self._bluetooth_driver = bluetooth_driver
        self._control_socket_path = control_socket_path

    async def run_proxy_init(self, script: str, timeout_sec: float) -> None:
        process = await asyncio.create_subprocess_shell(script)
        await asyncio.wait_for(process.wait(), timeout=timeout_sec)
        if process.returncode != 0:
            raise RuntimeError(f"proxy init exited with {process.returncode}")

    async def connect_speaker(
        self,
        *,
        controller_ready_timeout_sec: float,
        connect_retry_timeout_sec: float,
        retry_interval_sec: float,
    ) -> None:
        if self._bluetooth_driver is None:
            raise RuntimeError("bluetooth driver not configured")
        await self._wait_for_bluetooth_controller(
            timeout_sec=controller_ready_timeout_sec,
            retry_interval_sec=retry_interval_sec,
        )
        deadline = asyncio.get_running_loop().time() + connect_retry_timeout_sec
        while True:
            if await self._bluetooth_driver.ensure_connected():
                return
            if asyncio.get_running_loop().time() >= deadline:
                raise RuntimeError("bluetooth speaker connect retry budget exhausted")
            await asyncio.sleep(_next_sleep(deadline, retry_interval_sec))

    async def ensure_control_bridge(self, *, timeout_sec: float) -> None:
        if not self._control_socket_path:
            raise RuntimeError("control socket path not configured")
        response = await request_via_socket(
            self._control_socket_path,
            {
                "op": "query",
                "target": "runtime.status",
                "correlation_id": "startup-control-ready",
            },
            timeout_sec=timeout_sec,
        )
        if not response.get("ok", False):
            raise RuntimeError(str(response.get("error_message", "control bridge unavailable")))

    async def _wait_for_bluetooth_controller(
        self, *, timeout_sec: float, retry_interval_sec: float
    ) -> None:
        if self._bluetooth_driver is None:
            raise RuntimeError("bluetooth driver not configured")
        deadline = asyncio.get_running_loop().time() + timeout_sec
        while True:
            if await self._bluetooth_driver.health_check() == HealthState.HEALTHY:
                return
            if asyncio.get_running_loop().time() >= deadline:
                raise RuntimeError("bluetooth controller did not become ready")
            await asyncio.sleep(_next_sleep(deadline, retry_interval_sec))


class Supervisor:
    def __init__(
        self,
        *,
        session_id: str,
        bus: EventBus,
        modules: Iterable[CapabilityModule],
        bridges: Iterable[Bridge],
        health_interval_sec: float = 30.0,
        startup: StartupConfig | None = None,
        startup_runner: StartupRunner | None = None,
    ) -> None:
        self._session_id = session_id
        self._bus = bus
        self._modules = list(modules)
        self._bridges = list(bridges)
        self._health_interval_sec = max(health_interval_sec, 0.1)
        self._startup = startup or StartupConfig()
        self._startup_runner = startup_runner or SubprocessStartupRunner()
        self._health_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self._run_pre_startup_steps()
        for module in self._modules:
            await module.start(self._bus)
        for bridge in self._bridges:
            await bridge.start(self._bus)
        await self._run_post_startup_steps()
        await self._bus.publish(
            make_event(
                "system.startup",
                source="supervisor",
                session_id=self._session_id,
                payload={
                    "modules_loaded": [m.name for m in self._modules],
                    "bridges_loaded": [b.name for b in self._bridges],
                },
            )
        )
        await self.run_health_once()
        self._health_task = asyncio.create_task(self._run_health_loop())

    async def stop(self) -> None:
        if self._health_task is not None:
            self._health_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._health_task
            self._health_task = None
        for bridge in reversed(self._bridges):
            await bridge.stop()
        for module in reversed(self._modules):
            await module.stop()
        await self._bus.publish(
            make_event(
                "system.shutdown",
                source="supervisor",
                session_id=self._session_id,
                payload={"reason": "stop"},
            )
        )

    async def run_health_once(self) -> None:
        for component_type, items in (("module", self._modules), ("bridge", self._bridges)):
            for item in items:
                try:
                    health = await item.health_check()
                except Exception:
                    health = HealthState.UNAVAILABLE
                await self._bus.publish(
                    make_event(
                        "system.health_changed",
                        source="supervisor",
                        session_id=self._session_id,
                        payload={
                            "name": item.name,
                            "component_type": component_type,
                            "state": health.value,
                        },
                    )
                )

    async def _run_health_loop(self) -> None:
        while True:
            await asyncio.sleep(self._health_interval_sec)
            await self.run_health_once()

    async def _run_pre_startup_steps(self) -> None:
        if self._startup.configure_proxy_on_startup and self._startup.proxy_init_script:
            await self._run_startup_step(
                "proxy_init",
                self._startup_runner.run_proxy_init(
                    self._startup.proxy_init_script,
                    self._startup.proxy_init_timeout_sec,
                ),
            )
        if self._startup.connect_speaker_on_startup:
            await self._run_startup_step(
                "speaker_connect",
                self._startup_runner.connect_speaker(
                    controller_ready_timeout_sec=(
                        self._startup.bluetooth_controller_ready_timeout_sec
                    ),
                    connect_retry_timeout_sec=self._startup.bluetooth_connect_retry_timeout_sec,
                    retry_interval_sec=self._startup.bluetooth_retry_interval_sec,
                ),
            )

    async def _run_post_startup_steps(self) -> None:
        if self._startup.ensure_control_bridge_on_startup:
            await self._run_startup_step(
                "control_bridge_ready",
                self._startup_runner.ensure_control_bridge(
                    timeout_sec=self._startup.control_bridge_start_timeout_sec
                ),
            )

    async def _run_startup_step(self, step: str, operation: Awaitable[None]) -> None:
        try:
            await operation
        except Exception as exc:
            await self._bus.publish(
                make_event(
                    "system.startup_step_failed",
                    source="supervisor",
                    session_id=self._session_id,
                    payload={"step": step, "error": str(exc)},
                )
            )
            return
        await self._bus.publish(
            make_event(
                "system.startup_step_completed",
                source="supervisor",
                session_id=self._session_id,
                payload={"step": step},
            )
        )


def _next_sleep(deadline: float, retry_interval_sec: float) -> float:
    remaining = max(deadline - asyncio.get_running_loop().time(), 0.0)
    return min(max(retry_interval_sec, 0.01), remaining)
