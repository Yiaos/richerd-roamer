import asyncio

from roamerd.config.schema import StartupConfig
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.state_manager import HealthState, StateManager
from roamerd.runtime.supervisor import Supervisor


class HealthProbe:
    name = "motion"
    resource = "motion"
    events_produced: list[str] = []
    events_consumed: list[str] = []

    async def start(self, bus: EventBus) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def health_check(self) -> HealthState:
        return HealthState.UNAVAILABLE


def test_supervisor_publishes_periodic_health_updates() -> None:
    async def scenario() -> HealthState:
        bus = EventBus(session_id="s")
        state = StateManager(session_id="s")
        await state.start(bus)
        bus.start_background()
        supervisor = Supervisor(
            session_id="s",
            bus=bus,
            modules=[HealthProbe()],
            bridges=[],
            health_interval_sec=0.01,
        )
        await supervisor.start()
        await asyncio.sleep(0.03)
        await supervisor.stop()
        await bus.stop()
        return state.get_module_health("motion")

    assert asyncio.run(scenario()) == HealthState.UNAVAILABLE


def test_supervisor_runs_configured_startup_steps() -> None:
    class FakeStartupRunner:
        def __init__(self) -> None:
            self.calls: list[tuple[str, float]] = []

        async def run_proxy_init(self, script: str, timeout_sec: float) -> None:
            self.calls.append((script, timeout_sec))

    async def scenario() -> tuple[list[tuple[str, float]], list[str]]:
        bus = EventBus(session_id="s")
        runner = FakeStartupRunner()
        seen: list[str] = []

        async def handler(event):
            seen.append(str(event.payload.get("step")))

        bus.subscribe("system.startup_step_completed", handler)
        supervisor = Supervisor(
            session_id="s",
            bus=bus,
            modules=[],
            bridges=[],
            startup=StartupConfig(
                configure_proxy_on_startup=True,
                proxy_init_script="/opt/roamer/proxy.sh",
                proxy_init_timeout_sec=2.5,
            ),
            startup_runner=runner,
        )
        await supervisor.start()
        await bus.drain_once()
        await supervisor.stop()
        await bus.drain_once()
        return runner.calls, seen

    assert asyncio.run(scenario()) == (
        [("/opt/roamer/proxy.sh", 2.5)],
        ["proxy_init"],
    )


def test_supervisor_runs_speaker_connect_startup_step() -> None:
    class FakeStartupRunner:
        def __init__(self) -> None:
            self.calls: list[tuple[float, float, float]] = []

        async def run_proxy_init(self, script: str, timeout_sec: float) -> None:
            raise AssertionError("proxy init should not run")

        async def connect_speaker(
            self,
            *,
            controller_ready_timeout_sec: float,
            connect_retry_timeout_sec: float,
            retry_interval_sec: float,
        ) -> None:
            self.calls.append(
                (
                    controller_ready_timeout_sec,
                    connect_retry_timeout_sec,
                    retry_interval_sec,
                )
            )

    async def scenario() -> tuple[list[tuple[float, float, float]], list[str]]:
        bus = EventBus(session_id="s")
        runner = FakeStartupRunner()
        seen: list[str] = []

        async def handler(event):
            seen.append(str(event.payload.get("step")))

        bus.subscribe("system.startup_step_completed", handler)
        supervisor = Supervisor(
            session_id="s",
            bus=bus,
            modules=[],
            bridges=[],
            startup=StartupConfig(
                connect_speaker_on_startup=True,
                bluetooth_controller_ready_timeout_sec=1.5,
                bluetooth_connect_retry_timeout_sec=2.5,
                bluetooth_retry_interval_sec=0.25,
            ),
            startup_runner=runner,
        )
        await supervisor.start()
        await bus.drain_once()
        await supervisor.stop()
        await bus.drain_once()
        return runner.calls, seen

    assert asyncio.run(scenario()) == (
        [(1.5, 2.5, 0.25)],
        ["speaker_connect"],
    )


def test_supervisor_runs_control_bridge_readiness_startup_step_after_bridges_start() -> None:
    class ReadyBridge:
        name = "control"

        def __init__(self) -> None:
            self.started = False

        async def start(self, bus: EventBus) -> None:
            self.started = True

        async def stop(self) -> None:
            return None

        async def health_check(self) -> HealthState:
            return HealthState.HEALTHY

    class FakeStartupRunner:
        def __init__(self, bridge: ReadyBridge) -> None:
            self._bridge = bridge
            self.calls: list[tuple[float, bool]] = []

        async def run_proxy_init(self, script: str, timeout_sec: float) -> None:
            raise AssertionError("proxy init should not run")

        async def ensure_control_bridge(self, *, timeout_sec: float) -> None:
            self.calls.append((timeout_sec, self._bridge.started))

    async def scenario() -> tuple[list[tuple[float, bool]], list[str]]:
        bus = EventBus(session_id="s")
        bridge = ReadyBridge()
        runner = FakeStartupRunner(bridge)
        seen: list[str] = []

        async def handler(event):
            seen.append(str(event.payload.get("step")))

        bus.subscribe("system.startup_step_completed", handler)
        supervisor = Supervisor(
            session_id="s",
            bus=bus,
            modules=[],
            bridges=[bridge],
            startup=StartupConfig(
                ensure_control_bridge_on_startup=True,
                control_bridge_start_timeout_sec=3.5,
            ),
            startup_runner=runner,
        )
        await supervisor.start()
        await bus.drain_once()
        await supervisor.stop()
        await bus.drain_once()
        return runner.calls, seen

    assert asyncio.run(scenario()) == (
        [(3.5, True)],
        ["control_bridge_ready"],
    )
