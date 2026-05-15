import asyncio

from roamerd.events import Priority, make_event
from roamerd.kernel.event_bus import EventBus
from roamerd.runtime.safety_watchdog import SafetyWatchdog


def test_event_bus_priority_fifo_and_patterns() -> None:
    async def scenario() -> list[str]:
        bus = EventBus(session_id="s")
        seen: list[str] = []

        async def handler(event):
            seen.append(event.event_type + ":" + str(event.payload.get("n", "")))

        bus.subscribe_pattern("hearing.*", handler)
        await bus.publish(
            make_event(
                "hearing.low", source="t", session_id="s", priority=Priority.LOW, payload={"n": 1}
            )
        )
        await bus.publish(
            make_event(
                "hearing.high", source="t", session_id="s", priority=Priority.HIGH, payload={"n": 2}
            )
        )
        await bus.publish(
            make_event(
                "hearing.high", source="t", session_id="s", priority=Priority.HIGH, payload={"n": 3}
            )
        )
        await bus.drain_once()
        return seen

    assert asyncio.run(scenario()) == ["hearing.high:2", "hearing.high:3", "hearing.low:1"]


def test_event_bus_handler_exception_isolated() -> None:
    async def scenario() -> list[str]:
        bus = EventBus(session_id="s")
        seen: list[str] = []

        async def bad(event):
            raise RuntimeError("boom")

        async def good(event):
            seen.append(event.event_type)

        bus.subscribe("x.event", bad)
        bus.subscribe("x.event", good)
        await bus.publish(make_event("x.event", source="t", session_id="s"))
        await bus.drain_once()
        return seen

    assert asyncio.run(scenario()) == ["x.event"]


def test_event_bus_can_stop_immediately_after_background_start() -> None:
    async def scenario() -> bool:
        bus = EventBus(session_id="s")
        bus.start_background()
        await asyncio.wait_for(bus.stop(), timeout=0.2)
        return True

    assert asyncio.run(scenario()) is True


def test_event_bus_interrupts_long_noncritical_handler_for_critical_event() -> None:
    async def scenario() -> list[str]:
        bus = EventBus(session_id="s", handler_timeout_sec=1.0)
        seen: list[str] = []
        normal_started = asyncio.Event()

        async def normal_handler(event):
            seen.append("normal:start")
            normal_started.set()
            try:
                await asyncio.sleep(0.25)
            except asyncio.CancelledError:
                seen.append("normal:cancelled")
                raise
            seen.append("normal:end")

        async def critical_handler(event):
            seen.append("critical")

        bus.subscribe("normal.work", normal_handler)
        bus.subscribe("safety.stop", critical_handler)
        bus.start_background()
        await bus.publish(make_event("normal.work", source="t", session_id="s"))
        await normal_started.wait()
        await bus.publish(
            make_event("safety.stop", source="t", session_id="s", priority=Priority.CRITICAL)
        )
        await asyncio.sleep(0.15)
        await bus.stop()
        return seen

    seen = asyncio.run(scenario())
    assert seen[:3] == ["normal:start", "normal:cancelled", "critical"]


def test_safety_watchdog_triggers_callback_and_critical_event_for_stalled_dispatch() -> None:
    async def scenario() -> tuple[list[str], list[str]]:
        bus = EventBus(session_id="s", handler_timeout_sec=1.0)
        seen: list[str] = []
        stops: list[str] = []
        normal_calls = 0
        watchdog_seen = asyncio.Event()

        async def stop_motion() -> None:
            stops.append("stop")

        async def normal_handler(event):
            nonlocal normal_calls
            normal_calls += 1
            seen.append(f"normal:{normal_calls}:start")
            if normal_calls == 1:
                try:
                    await asyncio.sleep(1.0)
                except asyncio.CancelledError:
                    seen.append("normal:cancelled")
                    raise
            seen.append(f"normal:{normal_calls}:end")

        async def watchdog_handler(event):
            seen.append(event.event_type)
            watchdog_seen.set()

        watchdog = SafetyWatchdog(
            session_id="s",
            bus=bus,
            stop_motion=stop_motion,
            timeout_sec=0.05,
            interval_sec=0.01,
        )
        bus.subscribe("normal.work", normal_handler)
        bus.subscribe("system.watchdog_triggered", watchdog_handler)
        bus.start_background()
        watchdog.start()
        await bus.publish(make_event("normal.work", source="t", session_id="s"))
        await asyncio.wait_for(watchdog_seen.wait(), timeout=0.5)
        await asyncio.sleep(0.05)
        await watchdog.stop()
        await bus.stop()
        return seen, stops

    seen, stops = asyncio.run(scenario())
    assert seen[:3] == ["normal:1:start", "normal:cancelled", "system.watchdog_triggered"]
    assert stops == ["stop"]
