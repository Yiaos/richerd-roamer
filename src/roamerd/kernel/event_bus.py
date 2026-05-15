"""Priority ordered async event bus."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from itertools import count
from typing import DefaultDict
from uuid import uuid4

from roamerd.events.base import Event, Priority, make_event

EventHandler = Callable[[Event], Awaitable[None]]


@dataclass(frozen=True)
class Subscription:
    event_type: str
    handler: EventHandler
    id: str
    pattern: bool = False


class EventBus:
    """Serial event dispatcher with priority queues and pattern subscriptions."""

    def __init__(
        self,
        *,
        session_id: str,
        handler_timeout_sec: float = 5.0,
        critical_interrupt_after_sec: float = 0.1,
        normal_maxsize: int = 1024,
        low_maxsize: int = 256,
    ) -> None:
        self.session_id = session_id
        self._handler_timeout_sec = handler_timeout_sec
        self._critical_interrupt_after_sec = critical_interrupt_after_sec
        self._normal_maxsize = normal_maxsize
        self._low_maxsize = low_maxsize
        self._critical: deque[Event] = deque()
        self._high: asyncio.Queue[Event] = asyncio.Queue(maxsize=1024)
        self._normal: deque[Event] = deque()
        self._low: deque[Event] = deque()
        self._available = asyncio.Event()
        self._critical_arrived = asyncio.Event()
        self._stopping = False
        self._subscriptions: dict[str, Subscription] = {}
        self._exact: DefaultDict[str, list[str]] = defaultdict(list)
        self._patterns: list[str] = []
        self._seq = count()
        self._dispatch_task: asyncio.Task[None] | None = None
        self._dispatch_in_progress = False
        self._watchdog_triggered_for_current_dispatch = False
        self._last_dispatch_complete_at = time.monotonic()
        self.dropped_events: int = 0

    def subscribe(self, event_type: str, handler: EventHandler) -> Subscription:
        subscription = Subscription(event_type=event_type, handler=handler, id=uuid4().hex[:12])
        self._subscriptions[subscription.id] = subscription
        self._exact[event_type].append(subscription.id)
        return subscription

    def subscribe_pattern(self, pattern: str, handler: EventHandler) -> Subscription:
        subscription = Subscription(
            event_type=pattern, handler=handler, id=uuid4().hex[:12], pattern=True
        )
        self._subscriptions[subscription.id] = subscription
        self._patterns.append(subscription.id)
        return subscription

    def unsubscribe(self, subscription_id: str) -> None:
        subscription = self._subscriptions.pop(subscription_id, None)
        if subscription is None:
            return
        if subscription.pattern:
            self._patterns = [item for item in self._patterns if item != subscription_id]
        else:
            self._exact[subscription.event_type] = [
                item for item in self._exact[subscription.event_type] if item != subscription_id
            ]

    async def publish(self, event: Event) -> None:
        if event.priority == Priority.CRITICAL:
            self._critical.append(event)
            self._critical_arrived.set()
        elif event.priority == Priority.HIGH:
            await self._high.put(event)
        elif event.priority == Priority.NORMAL:
            if len(self._normal) >= self._normal_maxsize:
                dropped = self._normal.popleft()
                self.dropped_events += 1
                self._critical.append(self._overflow_event(dropped))
            self._normal.append(event)
        else:
            if len(self._low) >= self._low_maxsize:
                dropped = self._low.popleft()
                self.dropped_events += 1
                self._critical.append(self._overflow_event(dropped))
            self._low.append(event)
        self._available.set()

    async def run(self) -> None:
        self._last_dispatch_complete_at = time.monotonic()
        while not self._stopping or self._has_pending():
            event = await self._next_event()
            if event is None:
                continue
            await self._dispatch(event)

    def start_background(self) -> None:
        if self._dispatch_task is None or self._dispatch_task.done():
            self._stopping = False
            self._dispatch_task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        self._stopping = True
        self._available.set()
        if self._dispatch_task is not None:
            await self._dispatch_task

    async def drain_once(self) -> None:
        while self._has_pending():
            event = await self._next_event()
            if event is not None:
                await self._dispatch(event)

    async def _next_event(self) -> Event | None:
        while not self._has_pending():
            if self._stopping:
                return None
            self._available.clear()
            await self._available.wait()
        if self._critical:
            return self._critical.popleft()
        if not self._high.empty():
            return self._high.get_nowait()
        if self._normal:
            return self._normal.popleft()
        if self._low:
            return self._low.popleft()
        return None

    async def _dispatch(self, event: Event) -> None:
        self._dispatch_in_progress = True
        self._watchdog_triggered_for_current_dispatch = False
        if event.priority != Priority.CRITICAL and not self._critical:
            self._critical_arrived.clear()
        try:
            for subscription in self._matching_subscriptions(event.event_type):
                try:
                    interrupted = await self._run_handler(subscription, event)
                    if interrupted:
                        await self._requeue_event(event)
                        break
                except TimeoutError:
                    await self.publish(
                        make_event(
                            "system.handler_timeout",
                            source="event_bus",
                            session_id=self.session_id,
                            payload={
                                "handler": _handler_name(subscription.handler),
                                "event_type": event.event_type,
                                "timeout_ms": int(self._handler_timeout_sec * 1000),
                            },
                            priority=Priority.CRITICAL,
                        )
                    )
                except Exception as exc:
                    await self.publish(
                        make_event(
                            "system.handler_error",
                            source="event_bus",
                            session_id=self.session_id,
                            payload={
                                "handler": _handler_name(subscription.handler),
                                "event_type": event.event_type,
                                "exception_type": exc.__class__.__name__,
                                "message": str(exc),
                            },
                            priority=Priority.NORMAL,
                        )
                    )
        finally:
            self._dispatch_in_progress = False
            self._last_dispatch_complete_at = time.monotonic()
            self._watchdog_triggered_for_current_dispatch = False

    async def _run_handler(self, subscription: Subscription, event: Event) -> bool:
        if event.priority == Priority.CRITICAL:
            await asyncio.wait_for(
                subscription.handler(event),
                timeout=self._handler_timeout_sec,
            )
            return False

        started_at = time.monotonic()
        handler_task = asyncio.ensure_future(subscription.handler(event))
        critical_wait = asyncio.create_task(self._critical_arrived.wait())
        try:
            done, _ = await asyncio.wait(
                {handler_task, critical_wait},
                timeout=self._handler_timeout_sec,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if handler_task in done:
                await handler_task
                return False
            if critical_wait in done and self._critical:
                remaining = self._critical_interrupt_after_sec - (time.monotonic() - started_at)
                if remaining > 0:
                    done, _ = await asyncio.wait({handler_task}, timeout=remaining)
                    if handler_task in done:
                        await handler_task
                        return False
                handler_task.cancel()
                with suppress(asyncio.CancelledError):
                    await handler_task
                return True
            handler_task.cancel()
            with suppress(asyncio.CancelledError):
                await handler_task
            raise TimeoutError
        finally:
            critical_wait.cancel()
            with suppress(asyncio.CancelledError):
                await critical_wait

    def _matching_subscriptions(self, event_type: str) -> list[Subscription]:
        ids = list(self._exact.get(event_type, []))
        ids.extend(self._patterns)
        matches: list[Subscription] = []
        for subscription_id in ids:
            subscription = self._subscriptions.get(subscription_id)
            if subscription is None:
                continue
            if not subscription.pattern or _pattern_matches(subscription.event_type, event_type):
                matches.append(subscription)
        return matches

    def _has_pending(self) -> bool:
        return bool(self._critical or not self._high.empty() or self._normal or self._low)

    def dispatch_stall_elapsed_ms(self, timeout_sec: float) -> int | None:
        if not self._dispatch_in_progress or self._watchdog_triggered_for_current_dispatch:
            return None
        elapsed = time.monotonic() - self._last_dispatch_complete_at
        return int(elapsed * 1000) if elapsed > timeout_sec else None

    def mark_dispatch_watchdog_triggered(self) -> None:
        self._watchdog_triggered_for_current_dispatch = True

    def _overflow_event(self, dropped: Event) -> Event:
        next(self._seq)
        return make_event(
            "system.queue_overflow",
            source="event_bus",
            session_id=self.session_id,
            payload={
                "dropped_event_type": dropped.event_type,
                "priority": dropped.priority.wire_value,
            },
            priority=Priority.CRITICAL,
        )

    async def _requeue_event(self, event: Event) -> None:
        if event.priority == Priority.HIGH:
            await self._high.put(event)
        elif event.priority == Priority.NORMAL:
            self._normal.appendleft(event)
        elif event.priority == Priority.LOW:
            self._low.appendleft(event)
        self._available.set()


def _pattern_matches(pattern: str, event_type: str) -> bool:
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        return event_type.startswith(pattern[:-1])
    return pattern == event_type


def _handler_name(handler: EventHandler) -> str:
    return getattr(handler, "__qualname__", repr(handler))
