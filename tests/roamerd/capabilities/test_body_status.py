import pytest

from roamerd.capabilities.body_status import BodyStatusModule, BodyStatusSnapshot
from roamerd.events import Event
from roamerd.kernel import ActionManager, ActionRequestError, EventBus
from roamerd.kernel.action_manager import ActionStatus


class FakeBodyStatusProvider:
    async def snapshot(self) -> BodyStatusSnapshot:
        return BodyStatusSnapshot(
            hostname="roamer",
            uptime_sec=12.5,
            cpu_percent=10.0,
            memory_used_mb=100,
            memory_total_mb=1000,
            temperature_c=42.0,
            disk_used_mb=200,
            disk_total_mb=2000,
            network_interfaces=["lo0", "wlan0"],
            hardware_checks={
                "alsa": "ok",
                "bluetooth": "missing",
                "camera": "ok",
                "tailscale": "ok",
            },
        )


@pytest.mark.asyncio
async def test_body_status_sense_action_returns_legacy_shape() -> None:
    bus = EventBus()
    actions = ActionManager()
    module = BodyStatusModule(
        provider=FakeBodyStatusProvider(),
        action_manager=actions,
        session_id="session-1",
    )
    health_events: list[Event] = []

    async def handler(event: Event) -> None:
        health_events.append(event)

    bus.subscribe("system.health_changed", handler)
    await actions.start(bus)
    await module.start(bus)
    action = await actions.request_action("sense", {}, source_module="body")
    assert not isinstance(action, ActionRequestError)

    await bus.run_until_idle()

    completed = actions.get_action(action.action_id)
    assert completed.status is ActionStatus.COMPLETED
    assert completed.result["hostname"] == "roamer"
    assert completed.result["network_interfaces"] == ["lo0", "wlan0"]
    assert completed.result["hardware_checks"] == {
        "alsa": "ok",
        "bluetooth": "missing",
        "camera": "ok",
        "tailscale": "ok",
    }
    assert health_events[0].payload == {
        "component": "body",
        "status": "healthy",
    }


def test_body_status_snapshot_contains_legacy_field_set() -> None:
    snapshot = BodyStatusSnapshot(
        hostname="roamer",
        uptime_sec=12.5,
        cpu_percent=10.0,
        memory_used_mb=100,
        memory_total_mb=1000,
        temperature_c=42.0,
        disk_used_mb=200,
        disk_total_mb=2000,
        network_interfaces=["lo0", "wlan0"],
        hardware_checks={"camera": "ok"},
    )

    assert set(snapshot.model_dump()) == {
        "hostname",
        "uptime_sec",
        "cpu_percent",
        "memory_used_mb",
        "memory_total_mb",
        "temperature_c",
        "disk_used_mb",
        "disk_total_mb",
        "network_interfaces",
        "hardware_checks",
    }
