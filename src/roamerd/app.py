from __future__ import annotations

import tempfile
from pathlib import Path
from typing import cast
from uuid import uuid4

from roamerd.bridges.control.commands import ControlCommandRouter
from roamerd.bridges.control.server import ControlBridgeServer
from roamerd.capabilities.body_status import BodyStatusModule, LocalBodyStatusProvider
from roamerd.capabilities.hearing import HearingModule
from roamerd.capabilities.hearing.drivers.asr_base import BatchAsrDriver
from roamerd.capabilities.hearing.drivers.audio_capture_base import AudioCaptureDriver
from roamerd.capabilities.hearing.drivers.realtime_stt_base import RealtimeSttDriver
from roamerd.capabilities.hearing.drivers.vad_base import VadDriver
from roamerd.capabilities.hearing.drivers.wakeword_base import WakewordDriver
from roamerd.capabilities.motion import MotionModule
from roamerd.capabilities.motion.drivers.ros2_nav_base import MotionDriver
from roamerd.capabilities.reminder import ReminderModule
from roamerd.capabilities.speech import SpeechModule
from roamerd.capabilities.speech.drivers.bluetooth_base import BluetoothDriver
from roamerd.capabilities.speech.drivers.tts_base import TtsDriver
from roamerd.capabilities.speech.playback import PlaybackDriver
from roamerd.capabilities.vision import VisionModule
from roamerd.capabilities.vision.drivers.camera_base import CameraDriver
from roamerd.config.schema import RoamerdConfig
from roamerd.events import Event
from roamerd.kernel import (
    ActionManager,
    EventBus,
    PolicyEngine,
    PolicyRuleStore,
    StateManager,
    TraceLogger,
    TraceLoggerConfig,
    WorldModel,
)
from roamerd.runtime.driver_registry import load_driver
from roamerd.runtime.supervisor import Supervisor


class RoamerdApp:
    def __init__(
        self,
        *,
        config: RoamerdConfig,
        session_id: str,
        event_bus: EventBus,
        state_manager: StateManager,
        action_manager: ActionManager,
        policy_engine: PolicyEngine,
        world_model: WorldModel,
        observability: TraceLogger,
        supervisor: Supervisor,
    ) -> None:
        self.config = config
        self.session_id = session_id
        self.event_bus = event_bus
        self.state_manager = state_manager
        self.action_manager = action_manager
        self.policy_engine = policy_engine
        self.world_model = world_model
        self.observability = observability
        self.supervisor = supervisor

    async def start(self) -> None:
        await self.action_manager.start(self.event_bus)
        await self.state_manager.start(self.event_bus)
        await self.world_model.start(self.event_bus)
        await self.observability.start(self.event_bus)
        await self.policy_engine.start(
            self.event_bus,
            self.action_manager,
            self.state_manager,
            self.world_model,
        )
        await self.supervisor.start()
        await self.event_bus.publish(
            Event(
                event_type="system.module_ready",
                source="app",
                session_id=self.session_id,
                payload={"module": "kernel"},
            )
        )
        await self.event_bus.run_until_idle()

    async def stop(self) -> None:
        await self.supervisor.stop()
        await self.action_manager.stop()
        await self.event_bus.stop()
        self.observability.close()


def create_app(config: RoamerdConfig) -> RoamerdApp:
    session_id = uuid4().hex
    bus = EventBus(
        high_maxsize=config.kernel.event_bus.high_maxsize,
        normal_maxsize=config.kernel.event_bus.normal_maxsize,
        low_maxsize=config.kernel.event_bus.low_maxsize,
        handler_timeout_sec=config.kernel.event_bus.handler_timeout_sec,
        critical_fast_path_after_sec=config.kernel.event_bus.critical_fast_path_after_sec,
    )
    state = StateManager(
        session_id=session_id,
        playback_stale_after_sec=config.runtime.playback_stale_after_sec,
    )
    actions = ActionManager(session_id=session_id)
    world = WorldModel(static_places=config.world_model.places)
    policy = PolicyEngine(
        session_id=session_id,
        rules=PolicyRuleStore.from_config(config.policy.local_intents),
    )
    logger = TraceLogger(
        TraceLoggerConfig(log_dir=Path("logs")),
        session_id=session_id,
    )
    supervisor = Supervisor(bus)
    supervisor.register_module(
        HearingModule(
            wakeword=cast(
                WakewordDriver,
                load_driver(
                    "wakeword",
                    config.capabilities.hearing.wakeword.driver,
                    {
                        "min_interval_sec": config.capabilities.hearing.wakeword.min_interval_sec,
                        "wakeword": _first_wake_phrase(config),
                    },
                ),
            ),
            capture=cast(
                AudioCaptureDriver,
                load_driver(
                    "audio_capture",
                    config.capabilities.hearing.audio.driver,
                    {
                        "device": config.capabilities.hearing.alsa.capture_device,
                        "sample_rate": config.capabilities.hearing.alsa.sample_rate,
                        "channels": config.capabilities.hearing.alsa.channels,
                    },
                ),
            ),
            vad=cast(
                VadDriver,
                load_driver(
                    "vad",
                    config.capabilities.hearing.vad.driver,
                    {"threshold": config.capabilities.hearing.vad.silero.threshold},
                ),
            ),
            realtime_stt=cast(
                RealtimeSttDriver,
                load_driver(
                    "realtime_stt",
                    config.capabilities.hearing.stt.provider,
                    {
                        "url": config.capabilities.hearing.stt.url,
                        "timeout_sec": config.capabilities.hearing.stt.response_timeout_sec,
                    },
                ),
            ),
            batch_asr=cast(
                BatchAsrDriver,
                load_driver(
                    "batch_asr",
                    config.capabilities.hearing.stt.batch_driver,
                    {"model": config.capabilities.hearing.stt.model},
                ),
            ),
            state=state,
            action_manager=actions,
            session_id=session_id,
            wake_phrases=config.capabilities.hearing.wakeword.phrases,
        )
    )
    supervisor.register_module(
        SpeechModule(
            tts=cast(
                TtsDriver,
                load_driver(
                    "tts",
                    config.capabilities.speech.tts.primary,
                    {
                        "voice": config.capabilities.speech.tts.edge_voice,
                        "binary": config.capabilities.speech.tts.piper_binary,
                        "model": config.capabilities.speech.tts.piper_model,
                    },
                ),
            ),
            playback=cast(
                PlaybackDriver,
                load_driver(
                    "playback",
                    config.capabilities.speech.playback.driver,
                    {"device": config.capabilities.speech.alsa.playback_device},
                ),
            ),
            bluetooth=cast(
                BluetoothDriver,
                load_driver(
                    "bluetooth",
                    config.capabilities.speech.bluetooth.driver,
                    {"speaker_mac": config.capabilities.speech.bluetooth.speaker_mac or ""},
                ),
            ),
            action_manager=actions,
            output_dir=Path(tempfile.gettempdir()) / "roamerd-speech",
            session_id=session_id,
            bluetooth_timeout_sec=config.runtime.supervisor.startup.bluetooth_connect_retry_timeout_sec,
        )
    )
    supervisor.register_module(
        VisionModule(
            camera=cast(
                CameraDriver,
                load_driver(
                    "camera",
                    config.capabilities.vision.camera.driver,
                    {"device": config.capabilities.vision.camera.device},
                ),
            ),
            action_manager=actions,
            output_dir=Path(tempfile.gettempdir()) / "roamerd-vision",
            session_id=session_id,
            width=config.capabilities.vision.camera.width,
            height=config.capabilities.vision.camera.height,
        )
    )
    supervisor.register_module(
        BodyStatusModule(
            provider=LocalBodyStatusProvider(),
            action_manager=actions,
            session_id=session_id,
        )
    )
    supervisor.register_module(ReminderModule(action_manager=actions, session_id=session_id))
    supervisor.register_module(
        MotionModule(
            driver=cast(
                MotionDriver,
                load_driver("motion", config.capabilities.motion.driver),
            ),
            action_manager=actions,
            session_id=session_id,
        )
    )
    if config.bridges.control.enabled:
        supervisor.register_bridge(
            ControlBridgeServer(
                socket_path=Path(config.bridges.control.socket),
                router=ControlCommandRouter(
                    event_bus=bus,
                    action_manager=actions,
                    policy_engine=policy,
                    state_manager=state,
                ),
            )
        )
    return RoamerdApp(
        config=config,
        session_id=session_id,
        event_bus=bus,
        state_manager=state,
        action_manager=actions,
        policy_engine=policy,
        world_model=world,
        observability=logger,
        supervisor=supervisor,
    )


def _first_wake_phrase(config: RoamerdConfig) -> str:
    try:
        return config.capabilities.hearing.wakeword.phrases[0]
    except IndexError:
        return "wake"
