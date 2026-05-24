from datetime import UTC, datetime
from pathlib import Path

import pytest

from roamerd.capabilities.vision.drivers.camera_base import CameraDriver, CaptureResult
from roamerd.capabilities.vision.drivers.fswebcam import FswebcamCameraDriver
from roamerd.capabilities.vision.module import VisionModule
from roamerd.events import Event
from roamerd.kernel import ActionManager, ActionRequestError, EventBus
from roamerd.kernel.action_manager import ActionStatus


class FakeCameraDriver:
    async def capture(
        self,
        output_path: Path,
        *,
        width: int | None = None,
        height: int | None = None,
    ) -> CaptureResult:
        return CaptureResult(
            path=output_path,
            timestamp=datetime.now(UTC),
            width=width,
            height=height,
        )


def test_camera_protocol_accepts_fake_driver() -> None:
    camera: CameraDriver = FakeCameraDriver()

    assert camera is not None


@pytest.mark.asyncio
async def test_fswebcam_driver_invokes_subprocess_with_resolution(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    async def runner(command: list[str]) -> None:
        calls.append(command)
        Path(command[-1]).write_bytes(b"jpg")

    output = tmp_path / "capture.jpg"
    driver = FswebcamCameraDriver(device="/dev/video2", skip_frames=3, command_runner=runner)

    result = await driver.capture(output, width=640, height=480)

    assert result.path == output
    assert result.width == 640
    assert result.height == 480
    assert calls == [
        [
            "fswebcam",
            "--device",
            "/dev/video2",
            "--resolution",
            "640x480",
            "--skip",
            "3",
            str(output),
        ]
    ]


@pytest.mark.asyncio
async def test_fswebcam_driver_surfaces_camera_errors(tmp_path: Path) -> None:
    async def runner(command: list[str]) -> None:
        raise RuntimeError("camera busy")

    driver = FswebcamCameraDriver(command_runner=runner)

    with pytest.raises(RuntimeError, match="camera busy"):
        await driver.capture(tmp_path / "capture.jpg")


@pytest.mark.asyncio
async def test_vision_module_captures_watch_action(tmp_path: Path) -> None:
    bus = EventBus()
    actions = ActionManager()
    module = VisionModule(
        camera=FakeCameraDriver(),
        action_manager=actions,
        output_dir=tmp_path,
        session_id="session-1",
    )
    events: list[Event] = []

    async def handler(event: Event) -> None:
        events.append(event)

    bus.subscribe("vision.image_captured", handler)
    await actions.start(bus)
    await module.start(bus)
    action = await actions.request_action("watch", {}, resource="camera", source_module="vision")
    assert not isinstance(action, ActionRequestError)

    await bus.run_until_idle()

    assert module.name == "vision"
    assert await module.health_check() == "healthy"
    assert events[0].payload["path"] == str(tmp_path / f"{action.action_id}.jpg")
    assert actions.get_action(action.action_id).status is ActionStatus.COMPLETED
