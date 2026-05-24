import asyncio
import select
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest

from roamerd.app import RoamerdApp, create_app
from roamerd.capabilities.motion.drivers.ros2_nav import Ros2NavDriver
from roamerd.config.schema import RoamerdConfig
from roamerd.kernel import EventBus
from roamerd.runtime.supervisor import Supervisor


class FakeModule:
    name = "fake"
    events_produced = ["fake.ready"]
    events_consumed = ["system.startup"]
    resources = ["none"]

    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    async def start(self, bus: EventBus) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def health_check(self) -> str:
        return "healthy"


class FlakyModule(FakeModule):
    name = "flaky"

    def __init__(self, health: Callable[[], str]) -> None:
        super().__init__()
        self._health = health

    async def health_check(self) -> str:
        return self._health()


@pytest.mark.asyncio
async def test_supervisor_starts_and_stops_modules() -> None:
    bus = EventBus()
    supervisor = Supervisor(bus)
    module = FakeModule()
    supervisor.register_module(module)

    await supervisor.start()
    await supervisor.stop()

    assert module.started is True
    assert module.stopped is True


@pytest.mark.asyncio
async def test_supervisor_health_loop_degrades_failed_module_without_crashing() -> None:
    bus = EventBus()
    supervisor = Supervisor(bus, health_interval_sec=0.01)
    health = "healthy"
    module = FlakyModule(lambda: health)
    events = []

    async def handler(event):
        events.append(event)

    bus.subscribe("system.health_changed", handler)
    supervisor.register_module(module)

    await supervisor.start()
    health = "degraded"
    await asyncio.sleep(0.03)
    await bus.run_until_idle()
    await supervisor.stop()

    assert module.started is True
    assert module.stopped is True
    assert any(
        event.payload == {"component": "flaky", "status": "degraded"}
        for event in events
    )


def test_create_app_composes_kernel() -> None:
    app = create_app(RoamerdConfig())

    assert isinstance(app, RoamerdApp)
    assert app.event_bus is not None
    assert app.state_manager.snapshot().session_id


@pytest.mark.asyncio
async def test_app_start_stop_lifecycle() -> None:
    app = create_app(RoamerdConfig())

    await app.start()
    await app.stop()

    assert app.state_manager.snapshot().modules["kernel"] == "healthy"


@pytest.mark.asyncio
async def test_app_registers_mock_hearing_and_speech_modules() -> None:
    app = create_app(RoamerdConfig())

    await app.start()
    await app.stop()

    modules = app.state_manager.snapshot().modules
    assert modules["hearing"] == "healthy"
    assert modules["speech"] == "healthy"
    assert modules["vision"] == "healthy"
    assert modules["body"] == "healthy"
    assert modules["reminder"] == "healthy"
    assert modules["motion"] == "healthy"


@pytest.mark.asyncio
async def test_app_uses_configured_motion_driver_and_control_bridge() -> None:
    socket_path = Path(tempfile.mkdtemp(prefix="roamerd-", dir="/tmp")) / "roamer.sock"
    config = RoamerdConfig.model_validate(
        {
            "capabilities": {"motion": {"driver": "ros2_nav"}},
            "bridges": {"control": {"enabled": True, "socket": str(socket_path)}},
        }
    )
    app = create_app(config)

    await app.start()
    await app.stop()

    assert any(
        isinstance(module._driver, Ros2NavDriver)  # noqa: SLF001
        for module in app.supervisor.modules
        if module.name == "motion"
    )
    assert app.state_manager.snapshot().modules["control"] == "healthy"
    assert oct(socket_path.stat().st_mode & 0o777) == "0o600"


def test_module_entrypoint_runs_until_sigterm() -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "roamerd", "--config", "config/roamerd.yaml"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        ready, _, _ = select.select([process.stdout], [], [], 2)
        assert ready
        assert process.stdout.readline() == "roamerd started\n"
        assert process.poll() is None
        process.terminate()
        stdout, stderr = process.communicate(timeout=2)
    finally:
        if process.poll() is None:
            process.kill()

    assert process.returncode == 0, f"stdout={stdout}\nstderr={stderr}"
