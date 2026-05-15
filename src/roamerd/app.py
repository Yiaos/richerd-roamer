"""roamerd composition root."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from roamerd.bridges.base import Bridge
from roamerd.bridges.cognition.adapters import build_cognition_adapter
from roamerd.bridges.cognition.bridge import CognitionBridge, MockCognitionAdapter
from roamerd.bridges.control.bridge import ControlBridge
from roamerd.bridges.control.unix_socket import UnixSocketControlServer
from roamerd.bridges.discord.adapters import HttpDiscordAdapter
from roamerd.bridges.discord.bridge import DiscordBridge
from roamerd.bridges.memory.adapters import HttpMemoryAdapter
from roamerd.bridges.memory.bridge import MemoryBridge
from roamerd.capabilities.base import CapabilityModule
from roamerd.capabilities.body_status import BodyStatus
from roamerd.capabilities.body_status_module import BodyStatusModule
from roamerd.capabilities.hearing.drivers.legacy_batch import LegacyBatchSttDriver
from roamerd.capabilities.hearing.drivers.mock import MockSttDriver
from roamerd.capabilities.hearing.drivers.network_asr import (
    NetworkAsrDriver,
    NetworkThenBatchSttDriver,
)
from roamerd.capabilities.hearing.drivers.wakeword import build_wake_driver
from roamerd.capabilities.hearing.module import HearingModule, SttDriver
from roamerd.capabilities.motion.drivers.mock import MockRos2NavDriver
from roamerd.capabilities.motion.drivers.ros2_nav import Ros2NavDriver
from roamerd.capabilities.motion.module import MotionModule
from roamerd.capabilities.reminder import ReminderModule
from roamerd.capabilities.speech.drivers.legacy import (
    LegacyAlsaPlaybackDriver,
    LegacyBluezBluetoothDriver,
    LegacyTtsDriver,
)
from roamerd.capabilities.speech.drivers.mock import MockPlaybackDriver, MockTtsDriver
from roamerd.capabilities.speech.module import SpeechModule
from roamerd.capabilities.vision.drivers.fswebcam import FswebcamCameraDriver
from roamerd.capabilities.vision.drivers.mock import MockCameraDriver
from roamerd.capabilities.vision.module import VisionModule
from roamerd.config.schema import HearingConfig, RoamerdConfig
from roamerd.kernel.action_manager import ActionManager
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.observability import TraceLogger
from roamerd.kernel.policy_engine import PolicyEngine
from roamerd.kernel.state_manager import StateManager
from roamerd.kernel.world_model import WorldModel
from roamerd.runtime.safety_watchdog import SafetyWatchdog
from roamerd.runtime.supervisor import SubprocessStartupRunner, Supervisor


@dataclass
class RoamerdRuntime:
    session_id: str
    bus: EventBus
    state: StateManager
    actions: ActionManager
    world: WorldModel
    policy: PolicyEngine
    control: ControlBridge
    control_server: UnixSocketControlServer | None
    safety_watchdog: SafetyWatchdog
    supervisor: Supervisor
    observability: TraceLogger

    async def start(self) -> None:
        self.bus.start_background()
        self.safety_watchdog.start()
        await self.state.start(self.bus)
        await self.world.start(self.bus)
        await self.actions.start(self.bus)
        await self.observability.start(self.bus)
        await self.policy.start(self.bus)
        if self.control_server is not None:
            try:
                await self.control_server.start()
            except OSError as exc:
                self.control.mark_unavailable(str(exc))
        await self.supervisor.start()

    async def stop(self) -> None:
        if self.control_server is not None:
            await self.control_server.stop()
        await self.safety_watchdog.stop()
        await self.supervisor.stop()
        await self.bus.stop()
        self.observability.close()


def build_runtime(
    config: RoamerdConfig,
    *,
    mock_drivers: bool = True,
    control_socket_path: str | None = None,
) -> RoamerdRuntime:
    session_id = f"sess_{uuid4().hex[:12]}"
    bus = EventBus(session_id=session_id, handler_timeout_sec=config.kernel.handler_timeout_sec)
    state = StateManager(
        session_id=session_id, playback_stale_after_sec=config.kernel.state.playback_stale_after_sec
    )
    actions = ActionManager(session_id=session_id)
    world = WorldModel(config.world_model)
    body_status = BodyStatus()
    control = ControlBridge(session_id=session_id)
    motion_driver = MockRos2NavDriver() if mock_drivers else Ros2NavDriver()
    safety_watchdog = SafetyWatchdog(
        session_id=session_id,
        bus=bus,
        stop_motion=motion_driver.stop,
        timeout_sec=config.kernel.safety_watchdog_timeout_sec,
        interval_sec=config.kernel.safety_watchdog_interval_sec,
    )
    stt_driver = MockSttDriver() if mock_drivers else build_stt_driver(config.capabilities.hearing)
    wake_driver = None if mock_drivers else build_wake_driver(config.capabilities.hearing.wakeword)
    tts_driver = (
        MockTtsDriver() if mock_drivers else LegacyTtsDriver(config.capabilities.speech.tts)
    )
    playback_driver = (
        MockPlaybackDriver()
        if mock_drivers
        else LegacyAlsaPlaybackDriver(config.capabilities.speech.playback)
    )
    bluetooth_driver = (
        None if mock_drivers else LegacyBluezBluetoothDriver(config.capabilities.speech.bluetooth)
    )
    camera_driver = (
        MockCameraDriver()
        if mock_drivers
        else FswebcamCameraDriver(config.capabilities.vision.camera.fswebcam)
    )
    modules: list[CapabilityModule] = [
        HearingModule(
            session_id=session_id,
            action_manager=actions,
            stt_driver=stt_driver,
            wake_driver=wake_driver,
        ),
        SpeechModule(
            session_id=session_id,
            action_manager=actions,
            tts_driver=tts_driver,
            playback_driver=playback_driver,
            bluetooth_driver=bluetooth_driver,
        ),
        VisionModule(session_id=session_id, action_manager=actions, camera_driver=camera_driver),
        MotionModule(
            session_id=session_id,
            action_manager=actions,
            driver=motion_driver,
            wait_timeout_sec=config.capabilities.motion.wait_timeout_sec,
            poll_interval_sec=config.capabilities.motion.poll_interval_sec,
            arrival_tolerance=config.capabilities.motion.arrival_tolerance,
        ),
        BodyStatusModule(session_id=session_id, action_manager=actions),
        ReminderModule(session_id=session_id, action_manager=actions),
    ]
    cognition_adapter = (
        MockCognitionAdapter()
        if mock_drivers
        else build_cognition_adapter(
            driver=config.bridges.cognition.driver,
            endpoint=config.bridges.cognition.endpoint,
            timeout_sec=config.bridges.cognition.timeout_sec,
            fallback=config.bridges.cognition.fallback,
            local_endpoint=config.bridges.cognition.local_endpoint,
        )
    )
    memory_adapter = (
        None
        if mock_drivers or not config.bridges.memory.enabled
        else HttpMemoryAdapter(
            endpoint=config.bridges.memory.endpoint,
            timeout_sec=config.bridges.memory.timeout_sec,
        )
    )
    discord_adapter = (
        None
        if mock_drivers or not config.bridges.discord.enabled
        else HttpDiscordAdapter(
            channel_id=config.bridges.discord.channel_id,
            token_env=config.bridges.discord.token_env,
            timeout_sec=3.0,
        )
    )
    bridges: list[Bridge] = [
        control,
        CognitionBridge(session_id=session_id, adapter=cognition_adapter),
        DiscordBridge(
            session_id=session_id,
            enabled=config.bridges.discord.enabled,
            adapter=discord_adapter,
            source=config.bridges.discord.source,
            mention=(
                f"<@{config.bridges.discord.mention_user_id}>"
                if config.bridges.discord.mention_user_id
                else f"<@&{config.bridges.discord.mention_role_id}>"
                if config.bridges.discord.mention_role_id
                else config.bridges.discord.mention
            ),
            reply_instruction=config.bridges.discord.reply_instruction,
        ),
        MemoryBridge(
            session_id=session_id,
            buffer_path=config.bridges.memory.buffer_path,
            adapter=memory_adapter,
        ),
    ]
    policy = PolicyEngine(
        session_id=session_id,
        config=config.policy,
        state=state,
        actions=actions,
        world=world,
        body_status_snapshot=lambda full: body_status.snapshot(full=full),
    )
    observability = TraceLogger(
        config.runtime.logging,
        config.kernel.observability.privacy,
        session_id=session_id,
    )
    supervisor = Supervisor(
        session_id=session_id,
        bus=bus,
        modules=modules,
        bridges=bridges,
        health_interval_sec=config.runtime.supervisor.health_interval_sec,
        startup=config.runtime.supervisor.startup,
        startup_runner=SubprocessStartupRunner(
            bluetooth_driver=bluetooth_driver,
            control_socket_path=control_socket_path,
        ),
    )
    control_server = (
        UnixSocketControlServer(path=control_socket_path, bridge=control)
        if control_socket_path is not None
        else None
    )
    return RoamerdRuntime(
        session_id=session_id,
        bus=bus,
        state=state,
        actions=actions,
        world=world,
        policy=policy,
        control=control,
        control_server=control_server,
        safety_watchdog=safety_watchdog,
        supervisor=supervisor,
        observability=observability,
    )


def build_stt_driver(config: HearingConfig) -> SttDriver:
    batch = LegacyBatchSttDriver(audio=config.audio, funasr=config.stt.funasr)
    if config.stt.provider != "vllm_realtime" or config.stt.mode == "batch":
        return batch
    network = NetworkAsrDriver(
        url=config.stt.network_asr.url,
        model=config.stt.network_asr.model,
    )
    if config.stt.mode == "realtime_with_batch_fallback" or config.stt.fallback == "batch":
        return NetworkThenBatchSttDriver(primary=network, fallback=batch)
    return network
