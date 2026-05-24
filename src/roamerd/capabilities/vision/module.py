from __future__ import annotations

from pathlib import Path

from roamerd.capabilities.vision.drivers.camera_base import CameraDriver
from roamerd.events import Event
from roamerd.kernel import ActionManager, EventBus
from roamerd.types import JSONDict


class VisionModule:
    name = "vision"
    events_produced = ["vision.image_captured", "vision.capture_failed"]
    events_consumed = ["action.started"]
    resources = ["camera"]

    def __init__(
        self,
        *,
        camera: CameraDriver,
        action_manager: ActionManager | None = None,
        output_dir: Path,
        session_id: str = "session-1",
        width: int = 1280,
        height: int = 720,
    ) -> None:
        self._camera = camera
        self._actions = action_manager
        self._output_dir = output_dir
        self._session_id = session_id
        self._width = width
        self._height = height
        self._bus: EventBus | None = None

    async def start(self, bus: EventBus) -> None:
        self._bus = bus
        self._output_dir.mkdir(parents=True, exist_ok=True)
        bus.subscribe("action.started", self._handle_action_started)

    async def stop(self) -> None:
        return None

    async def health_check(self) -> str:
        return "healthy"

    async def _handle_action_started(self, event: Event) -> None:
        if event.payload.get("action_type") not in {"watch", "vision.capture", "capture"}:
            return
        action_id = event.action_id or str(event.payload.get("action_id", ""))
        output_path = self._output_dir / f"{action_id}.jpg"
        try:
            result = await self._camera.capture(
                output_path,
                width=self._width,
                height=self._height,
            )
            await self._publish(
                "vision.image_captured",
                {
                    "path": str(result.path),
                    "width": result.width or self._width,
                    "height": result.height or self._height,
                },
                action_id=action_id,
                turn_id=event.turn_id,
            )
            if self._actions is not None:
                await self._actions.complete_action(action_id, {"path": str(result.path)})
        except Exception as exc:
            await self._publish(
                "vision.capture_failed",
                {"error_code": "CAPTURE_FAILED", "message": str(exc)},
                action_id=action_id,
                turn_id=event.turn_id,
            )
            if self._actions is not None:
                await self._actions.fail_action(
                    action_id,
                    {"error_code": "CAPTURE_FAILED", "message": str(exc)},
                )

    async def _publish(
        self,
        event_type: str,
        payload: JSONDict,
        *,
        action_id: str,
        turn_id: str | None,
    ) -> None:
        if self._bus is None:
            return
        await self._bus.publish(
            Event(
                event_type=event_type,
                source="vision",
                session_id=self._session_id,
                action_id=action_id,
                turn_id=turn_id,
                payload=payload,
            )
        )
