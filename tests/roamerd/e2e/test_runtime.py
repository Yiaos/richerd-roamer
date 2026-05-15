import asyncio
import os
from pathlib import Path

from roamerd.app import build_runtime
from roamerd.bridges.control.unix_socket import request_via_socket
from roamerd.compat.legacy_config import load_config
from roamerd.events import make_event
from roamerd.events.control import ControlCommandPayload, WaitMode


def test_runtime_starts_and_control_query_works() -> None:
    async def scenario() -> bool:
        runtime = build_runtime(load_config(), mock_drivers=True)
        await runtime.start()
        response = await runtime.control.query("runtime.status")
        await runtime.stop()
        return bool(response.get("ok"))

    assert asyncio.run(scenario()) is True


def test_runtime_sense_action_completes_through_control_bridge() -> None:
    async def scenario() -> bool:
        runtime = build_runtime(load_config(), mock_drivers=True)
        await runtime.start()
        response = await runtime.control.request(
            ControlCommandPayload(
                op="run",
                action="sense",
                args={"full": True},
                wait=WaitMode.COMPLETED,
                correlation_id="sense-1",
            )
        )
        await runtime.stop()
        result = response.get("result")
        return bool(response.get("ok")) and isinstance(result, dict) and "hostname" in result

    assert asyncio.run(scenario()) is True


def test_runtime_stable_control_queries() -> None:
    async def scenario() -> dict[str, bool]:
        runtime = build_runtime(load_config(), mock_drivers=True)
        await runtime.start()
        body = await runtime.control.query("body.status")
        world = await runtime.control.query("world.position")
        actions = await runtime.control.query("actions.list")
        health = await runtime.control.query("health")
        await runtime.stop()
        return {
            "body": bool(body.get("ok")) and "hostname" in body.get("result", {}),
            "world": bool(world.get("ok")) and "position" in world.get("result", {}),
            "actions": bool(actions.get("ok")) and "actions" in actions.get("result", {}),
            "health": bool(health.get("ok")) and "modules" in health.get("result", {}),
        }

    assert asyncio.run(scenario()) == {
        "body": True,
        "world": True,
        "actions": True,
        "health": True,
    }


def test_body_status_query_exposes_body_telemetry_shape() -> None:
    async def scenario() -> dict[str, object]:
        runtime = build_runtime(load_config(), mock_drivers=True)
        await runtime.start()
        await runtime.bus.publish(
            make_event(
                "motion.status_updated",
                source="test",
                session_id=runtime.session_id,
                payload={"battery_percent": 87, "docked": True},
            )
        )
        await runtime.bus.drain_once()
        response = await runtime.control.query("body.status")
        await runtime.stop()
        result = response.get("result")
        assert isinstance(result, dict)
        return result

    body = asyncio.run(scenario())
    assert body["battery"] == {"level": 87, "charging": None}
    assert body["dock"] == {"state": "docked"}
    assert body["thermal"] == {"pi": None}
    network = body["network"]
    assert isinstance(network, dict)
    assert network["state"] == "unknown"
    assert body["ros2"] == {"state": "healthy"}
    assert body["base"] == {"estop": False, "faults": []}
    capabilities = body["capabilities"]
    assert isinstance(capabilities, dict)
    assert capabilities["motion"] == "healthy"


def test_runtime_serves_unix_socket_queries() -> None:
    async def scenario() -> bool:
        socket_path = Path(f"/tmp/roamerd-test-{os.getpid()}.sock")
        socket_path.unlink(missing_ok=True)
        runtime = build_runtime(
            load_config(), mock_drivers=True, control_socket_path=str(socket_path)
        )
        await runtime.start()
        response = await request_via_socket(
            str(socket_path),
            {"op": "query", "target": "runtime.status", "correlation_id": "sock-1"},
        )
        await runtime.stop()
        socket_path.unlink(missing_ok=True)
        return bool(response.get("ok"))

    assert asyncio.run(scenario()) is True


def test_runtime_serves_legacy_converse_socket_command() -> None:
    async def scenario() -> dict[str, object]:
        socket_path = Path(f"/tmp/roamerd-converse-{os.getpid()}.sock")
        socket_path.unlink(missing_ok=True)
        config = load_config()
        config.runtime.supervisor.startup.configure_proxy_on_startup = False
        config.runtime.supervisor.startup.connect_speaker_on_startup = False
        runtime = build_runtime(config, mock_drivers=True, control_socket_path=str(socket_path))
        await runtime.start()
        await runtime.bus.drain_once()
        response = await request_via_socket(
            str(socket_path),
            {
                "command": "converse",
                "args": {"timeout": 1.0, "use_wakeword": False},
                "timeout_sec": 2,
                "request_id": "legacy-converse-1",
            },
        )
        await runtime.stop()
        socket_path.unlink(missing_ok=True)
        return response

    response = asyncio.run(scenario())
    assert response["ok"] is True
    assert response["state"] == "completed"
    assert response["request_id"] == "legacy-converse-1"
    assert isinstance(response["result"], dict)
    assert "text" in response["result"]


def test_runtime_keeps_running_when_control_socket_cannot_start() -> None:
    async def scenario() -> str:
        socket_path = Path(f"/tmp/roamerd-socket-dir-{os.getpid()}")
        socket_path.mkdir(exist_ok=True)
        runtime = build_runtime(
            load_config(), mock_drivers=True, control_socket_path=str(socket_path)
        )
        started = False
        try:
            await runtime.start()
            started = True
            await runtime.bus.drain_once()
            health = runtime.state.get_bridge_health("control")
            response = await runtime.control.query("runtime.status")
            assert response["ok"] is True
            return health.value
        finally:
            if started:
                await runtime.stop()
            else:
                await runtime.bus.stop()
                runtime.observability.close()
            socket_path.rmdir()

    assert asyncio.run(scenario()) == "unavailable"


def test_runtime_startup_can_probe_control_socket_readiness() -> None:
    async def scenario() -> list[str]:
        socket_path = Path(f"/tmp/roamerd-ready-{os.getpid()}.sock")
        socket_path.unlink(missing_ok=True)
        config = load_config()
        config.runtime.supervisor.startup.configure_proxy_on_startup = False
        config.runtime.supervisor.startup.connect_speaker_on_startup = False
        config.runtime.supervisor.startup.ensure_control_bridge_on_startup = True
        config.runtime.supervisor.startup.control_bridge_start_timeout_sec = 1.0
        runtime = build_runtime(
            config,
            mock_drivers=True,
            control_socket_path=str(socket_path),
        )
        seen: list[str] = []

        async def handler(event):
            seen.append(str(event.payload.get("step")))

        runtime.bus.subscribe("system.startup_step_completed", handler)
        await runtime.start()
        await runtime.bus.drain_once()
        await runtime.stop()
        socket_path.unlink(missing_ok=True)
        return seen

    assert asyncio.run(scenario()) == ["control_bridge_ready"]


def test_runtime_wires_safety_watchdog_to_motion_driver_stop() -> None:
    async def scenario() -> tuple[list[str], bool]:
        config = load_config()
        config.runtime.supervisor.startup.configure_proxy_on_startup = False
        runtime = build_runtime(config, mock_drivers=True)
        runtime.safety_watchdog._timeout_sec = 0.05
        runtime.safety_watchdog._interval_sec = 0.01
        seen: list[str] = []
        normal_calls = 0

        async def slow_handler(event):
            nonlocal normal_calls
            normal_calls += 1
            if normal_calls == 1:
                await asyncio.sleep(1.0)

        async def watchdog_handler(event):
            seen.append(event.event_type)

        runtime.bus.subscribe("normal.work", slow_handler)
        runtime.bus.subscribe("system.watchdog_triggered", watchdog_handler)
        await runtime.start()
        await runtime.bus.publish(make_event("normal.work", source="test", session_id="s"))
        await asyncio.sleep(0.2)
        motion_module = next(
            module for module in runtime.supervisor._modules if module.name == "motion"
        )
        driver = motion_module._driver
        stopped_before_shutdown = bool(driver.stopped)
        await runtime.stop()
        return seen, stopped_before_shutdown

    assert asyncio.run(scenario()) == (["system.watchdog_triggered"], True)
