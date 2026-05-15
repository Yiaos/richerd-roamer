"""Vision capture module."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Protocol, runtime_checkable

from roamerd.events.base import Event, make_event
from roamerd.events.vision import PersonPayload, ScenePayload
from roamerd.kernel.action_manager import ActionManager
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.state_manager import HealthState


@runtime_checkable
class CameraDriver(Protocol):
    async def capture(
        self, *, output: str | None = None, width: int | None = None, height: int | None = None
    ) -> dict[str, object]: ...

    async def health_check(self) -> HealthState: ...


class VisionModule:
    name = "camera"
    resource = "camera"
    events_produced = [
        "vision.image_captured",
        "vision.scene_observed",
        "vision.person_detected",
        "vision.capture_failed",
    ]
    events_consumed = [
        "action.started",
        "action.cancelled",
        "action.preempted",
        "system.shutdown_requested",
    ]

    def __init__(
        self, *, session_id: str, action_manager: ActionManager, camera_driver: CameraDriver
    ) -> None:
        self._session_id = session_id
        self._actions = action_manager
        self._camera = camera_driver
        self._bus: EventBus | None = None
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def start(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe("action.started", self._on_action_started)
        bus.subscribe("action.cancelled", self._on_action_stopped)
        bus.subscribe("action.preempted", self._on_action_stopped)
        bus.subscribe("system.shutdown_requested", self._on_shutdown_requested)
        await bus.publish(
            make_event(
                "system.module_ready",
                source="vision_module",
                session_id=self._session_id,
                payload={"name": self.name, "component_type": "module", "state": "healthy"},
            )
        )

    async def stop(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()

    async def health_check(self) -> HealthState:
        return await self._camera.health_check()

    async def _on_action_started(self, event: Event) -> None:
        if event.payload.get("action_type") not in {"watch", "capture"} or self._bus is None:
            return
        action_id = event.action_id or ""
        task = asyncio.create_task(self._run_capture(event))
        self._tasks[action_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(action_id, None))

    async def _run_capture(self, event: Event) -> None:
        if self._bus is None:
            return
        args = event.payload.get("payload")
        payload = args if isinstance(args, dict) else {}
        action_id = event.action_id or ""
        result = await self._camera.capture(
            output=str(payload["output"]) if payload.get("output") else None,
            width=int(payload["width"]) if isinstance(payload.get("width"), int) else None,
            height=int(payload["height"]) if isinstance(payload.get("height"), int) else None,
        )
        if result.get("ok", False):
            width_raw = result.get("width", 0)
            height_raw = result.get("height", 0)
            image = {
                "action_id": action_id,
                "path": str(result.get("path", "")),
                "width": width_raw if isinstance(width_raw, int) else 0,
                "height": height_raw if isinstance(height_raw, int) else 0,
            }
            await self._bus.publish(
                make_event(
                    "vision.image_captured",
                    source="vision_module",
                    session_id=self._session_id,
                    action_id=action_id,
                    payload=image,
                )
            )
            await self._publish_people(action_id, result)
            await self._publish_scene(action_id, result)
            await self._actions.complete_action(action_id, image)
        else:
            error = {
                "error_code": "camera.capture.failed",
                "error_message": str(result.get("error", "")),
            }
            await self._bus.publish(
                make_event(
                    "vision.capture_failed",
                    source="vision_module",
                    session_id=self._session_id,
                    action_id=action_id,
                    payload=error,
                )
            )
            await self._actions.fail_action(action_id, error)

    async def _on_action_stopped(self, event: Event) -> None:
        if event.payload.get("action_type") not in {"watch", "capture"}:
            return
        task = self._tasks.get(event.action_id or "")
        if task is not None:
            task.cancel()

    async def _on_shutdown_requested(self, event: Event) -> None:
        await self.stop()

    async def _publish_people(self, action_id: str, result: dict[str, object]) -> None:
        if self._bus is None:
            return
        people = result.get("people")
        if not isinstance(people, list):
            return
        for item in people:
            if not isinstance(item, dict):
                continue
            person = PersonPayload.model_validate(item)
            await self._bus.publish(
                make_event(
                    "vision.person_detected",
                    source="vision_module",
                    session_id=self._session_id,
                    action_id=action_id,
                    payload=person.model_dump(mode="json"),
                )
            )

    async def _publish_scene(self, action_id: str, result: dict[str, object]) -> None:
        if self._bus is None:
            return
        objects_raw = result.get("objects")
        description_raw = result.get("description")
        has_objects = isinstance(objects_raw, list) and len(objects_raw) > 0
        has_description = isinstance(description_raw, str) and bool(description_raw.strip())
        if not has_objects and not has_description:
            return
        description = description_raw.strip() if isinstance(description_raw, str) else None
        path = str(result.get("path", ""))
        scene = ScenePayload(
            description=description if has_description else None,
            objects=[str(item) for item in objects_raw] if isinstance(objects_raw, list) else [],
            image_path=path,
            model=str(result.get("model", "local")),
        )
        await self._bus.publish(
            make_event(
                "vision.scene_observed",
                source="vision_module",
                session_id=self._session_id,
                action_id=action_id,
                payload=scene.model_dump(mode="json"),
            )
        )
