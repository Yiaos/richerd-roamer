from __future__ import annotations

import asyncio
import fnmatch
import inspect
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from roamerd.events import Event, Priority

EventHandler = Callable[[Event], Awaitable[None]]


@dataclass(frozen=True)
class Subscription:
    id: str
    event_type: str
    handler: EventHandler
    pattern: bool = False


class EventBus:
    def __init__(
        self,
        *,
        high_maxsize: int = 1024,
        normal_maxsize: int = 1024,
        low_maxsize: int = 256,
        handler_timeout_sec: float = 5.0,
        critical_fast_path_after_sec: float = 0.1,
        watchdog_interval_sec: float = 0.1,
        watchdog_stall_after_sec: float = 1.0,
    ) -> None:
        self._queues: dict[Priority, deque[Event]] = {
            Priority.CRITICAL: deque(),
            Priority.HIGH: deque(),
            Priority.NORMAL: deque(),
            Priority.LOW: deque(),
        }
        self._maxsizes = {
            Priority.CRITICAL: 0,
            Priority.HIGH: high_maxsize,
            Priority.NORMAL: normal_maxsize,
            Priority.LOW: low_maxsize,
        }
        self._subscriptions: dict[str, Subscription] = {}
        self._condition = asyncio.Condition()
        self._critical_arrived = asyncio.Event()
        self._handler_timeout_sec = handler_timeout_sec
        self._critical_fast_path_after_sec = critical_fast_path_after_sec
        self._watchdog_interval_sec = watchdog_interval_sec
        self._watchdog_stall_after_sec = watchdog_stall_after_sec
        self._watchdog_task: asyncio.Task[None] | None = None
        self._current_handler_started_at: float | None = None
        self._watchdog_reported_current_handler = False
        self._stopped = False

    def subscribe(self, event_type: str, handler: EventHandler) -> Subscription:
        return self._subscribe(event_type, handler, pattern=False)

    def subscribe_pattern(self, pattern: str, handler: EventHandler) -> Subscription:
        return self._subscribe(pattern, handler, pattern=True)

    def unsubscribe(self, subscription_id: str) -> None:
        self._subscriptions.pop(subscription_id, None)

    async def publish(self, event: Event) -> None:
        overflow_event: Event | None = None
        async with self._condition:
            queue = self._queues[event.priority]
            maxsize = self._maxsizes[event.priority]
            if event.priority is Priority.HIGH:
                while maxsize > 0 and len(queue) >= maxsize:
                    await self._condition.wait()
            elif maxsize > 0 and len(queue) >= maxsize:
                dropped = queue.popleft()
                if event.priority in {Priority.NORMAL, Priority.LOW}:
                    overflow_event = Event(
                        event_type="system.queue_overflow",
                        source="event_bus",
                        session_id=event.session_id,
                        priority=Priority.NORMAL,
                        payload={
                            "priority": event.priority.value,
                            "dropped_event_type": dropped.event_type,
                        },
                    )
            queue.append(event)
            if event.priority is Priority.CRITICAL:
                self._critical_arrived.set()
            self._condition.notify_all()
        if overflow_event is not None:
            await self.publish(overflow_event)

    async def run_until_idle(self) -> None:
        while True:
            event = await self._pop_next(block=False)
            if event is None:
                return
            await self._dispatch(event)

    async def run(self) -> None:
        self._stopped = False
        self._watchdog_task = asyncio.create_task(self._safety_watchdog())
        try:
            while True:
                event = await self._pop_next(block=not self._stopped)
                if event is None:
                    return
                await self._dispatch(event)
        finally:
            await self._stop_watchdog()

    async def stop(self) -> None:
        self._stopped = True
        async with self._condition:
            self._condition.notify_all()
        await self.run_until_idle()
        await self._stop_watchdog()

    def _subscribe(
        self,
        event_type: str,
        handler: EventHandler,
        *,
        pattern: bool,
    ) -> Subscription:
        if not inspect.iscoroutinefunction(handler):
            raise TypeError("EventBus handlers must be async callables")
        subscription = Subscription(
            id=uuid4().hex,
            event_type=event_type,
            handler=handler,
            pattern=pattern,
        )
        self._subscriptions[subscription.id] = subscription
        return subscription

    async def _pop_next(self, *, block: bool) -> Event | None:
        async with self._condition:
            while True:
                event = self._pop_next_locked()
                if event is not None:
                    self._condition.notify_all()
                    return event
                if not block or self._stopped:
                    return None
                await self._condition.wait()

    def _pop_next_locked(self) -> Event | None:
        for priority in (Priority.CRITICAL, Priority.HIGH, Priority.NORMAL, Priority.LOW):
            queue = self._queues[priority]
            if queue:
                event = queue.popleft()
                if priority is Priority.CRITICAL and not queue:
                    self._critical_arrived.clear()
                return event
        return None

    async def _requeue_front(self, event: Event) -> None:
        async with self._condition:
            self._queues[event.priority].appendleft(event)
            self._condition.notify_all()

    async def _dispatch(self, event: Event) -> None:
        for subscription in list(self._subscriptions.values()):
            if not self._matches(subscription, event.event_type):
                continue
            requeued = await self._run_handler(subscription, event)
            if requeued:
                return

    async def _run_handler(self, subscription: Subscription, event: Event) -> bool:
        task: asyncio.Future[None] = asyncio.ensure_future(subscription.handler(event))
        started_at = time.monotonic()
        self._current_handler_started_at = started_at
        self._watchdog_reported_current_handler = False
        critical_waiter: asyncio.Task[bool] | None = None
        if event.priority is not Priority.CRITICAL:
            critical_waiter = asyncio.create_task(self._critical_arrived.wait())
        try:
            while not task.done():
                elapsed = time.monotonic() - started_at
                if elapsed >= self._handler_timeout_sec:
                    task.cancel()
                    await self._wait_cancelled(task)
                    await self._emit_handler_timeout(event, subscription)
                    return False
                if (
                    critical_waiter is not None
                    and self._critical_arrived.is_set()
                    and elapsed >= self._critical_fast_path_after_sec
                ):
                    task.cancel()
                    await self._wait_cancelled(task)
                    await self._requeue_front(event)
                    return True
                wait_for = min(
                    max(self._critical_fast_path_after_sec - elapsed, 0.001),
                    max(self._handler_timeout_sec - elapsed, 0.001),
                )
                wait_tasks: list[asyncio.Future[Any]] = [task]
                if critical_waiter is not None:
                    wait_tasks.append(critical_waiter)
                await asyncio.wait(
                    wait_tasks,
                    timeout=wait_for,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            try:
                await task
            except Exception:
                return False
            return False
        finally:
            self._current_handler_started_at = None
            self._watchdog_reported_current_handler = False
            if critical_waiter is not None:
                critical_waiter.cancel()

    async def _safety_watchdog(self) -> None:
        try:
            while not self._stopped:
                await asyncio.sleep(self._watchdog_interval_sec)
                started_at = self._current_handler_started_at
                if started_at is None or self._watchdog_reported_current_handler:
                    continue
                elapsed = time.monotonic() - started_at
                if elapsed < self._watchdog_stall_after_sec:
                    continue
                self._watchdog_reported_current_handler = True
                await self.publish(
                    Event(
                        event_type="system.watchdog_triggered",
                        source="event_bus",
                        session_id="",
                        priority=Priority.CRITICAL,
                        payload={"stalled_for_sec": elapsed},
                    )
                )
        except asyncio.CancelledError:
            return

    async def _stop_watchdog(self) -> None:
        if self._watchdog_task is None:
            return
        self._watchdog_task.cancel()
        try:
            await self._watchdog_task
        except asyncio.CancelledError:
            pass
        self._watchdog_task = None

    async def _emit_handler_timeout(self, event: Event, subscription: Subscription) -> None:
        await self.publish(
            Event(
                event_type="system.handler_timeout",
                source="event_bus",
                session_id=event.session_id,
                priority=Priority.NORMAL,
                payload={
                    "event_type": event.event_type,
                    "handler": subscription.id,
                    "timeout_sec": self._handler_timeout_sec,
                },
            )
        )

    @staticmethod
    async def _wait_cancelled(task: asyncio.Future[None]) -> None:
        try:
            await task
        except asyncio.CancelledError:
            return
        except Exception:
            return

    @staticmethod
    def _matches(subscription: Subscription, event_type: str) -> bool:
        if subscription.pattern:
            return fnmatch.fnmatchcase(event_type, subscription.event_type)
        return subscription.event_type == event_type
