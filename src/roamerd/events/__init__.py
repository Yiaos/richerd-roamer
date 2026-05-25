from roamerd.events.action import (
    ActionCancelled,
    ActionCancelRequested,
    ActionCompleted,
    ActionDetached,
    ActionFailed,
    ActionPreempted,
    ActionPreemptRequested,
    ActionStarted,
)
from roamerd.events.base import Event, Priority
from roamerd.events.cognition import (
    CognitionRequestNeeded,
    CognitionResponseReceived,
    CognitionUnavailable,
)
from roamerd.events.control import (
    ControlCommandReceived,
    ControlResponseReady,
    ControlResponseSent,
)
from roamerd.events.hearing import (
    AudioLevelChanged,
    ListenFailed,
    RecordingStarted,
    SpeechEndpointDetected,
    TranscriptReady,
    WakeTriggered,
)

# Typed payload classes are the canonical schema contracts for module/bridge payloads.
# Producers still publish generic Event envelopes during the cutover; tests keep these
# typed schemas aligned with the payloads emitted by the current string-based path.
from roamerd.events.memory import MemoryCandidateRaised, MemoryFlushFailed, PolicyUpdate
from roamerd.events.motion import (
    MotionCompleted,
    MotionFailed,
    MotionPositionUpdated,
    MotionStarted,
    MotionStatusUpdated,
    MotionStopRequested,
)
from roamerd.events.safety import (
    EmergencyStopRequested,
    SafetyStopApplied,
    SafetyTriggered,
)
from roamerd.events.speech import (
    PlaybackCompleted,
    PlaybackFailed,
    PlaybackStarted,
    SpeechStopRequested,
    SynthesisStarted,
)
from roamerd.events.system import (
    HandlerTimeout,
    HealthChanged,
    ModuleReady,
    QueueOverflow,
    Shutdown,
    ShutdownRequested,
    Startup,
    WatchdogTriggered,
)
from roamerd.events.vision import (
    CaptureFailed,
    ImageCaptured,
    PersonDetected,
    SceneObserved,
)

__all__ = [
    "ActionCancelRequested",
    "ActionCancelled",
    "ActionCompleted",
    "ActionDetached",
    "ActionFailed",
    "ActionPreemptRequested",
    "ActionPreempted",
    "ActionStarted",
    "AudioLevelChanged",
    "CaptureFailed",
    "CognitionRequestNeeded",
    "CognitionResponseReceived",
    "CognitionUnavailable",
    "ControlCommandReceived",
    "ControlResponseReady",
    "ControlResponseSent",
    "EmergencyStopRequested",
    "Event",
    "HandlerTimeout",
    "HealthChanged",
    "ImageCaptured",
    "ListenFailed",
    "MemoryCandidateRaised",
    "MemoryFlushFailed",
    "ModuleReady",
    "MotionCompleted",
    "MotionFailed",
    "MotionPositionUpdated",
    "MotionStarted",
    "MotionStatusUpdated",
    "MotionStopRequested",
    "PersonDetected",
    "PlaybackCompleted",
    "PlaybackFailed",
    "PlaybackStarted",
    "PolicyUpdate",
    "Priority",
    "QueueOverflow",
    "RecordingStarted",
    "SafetyStopApplied",
    "SafetyTriggered",
    "SceneObserved",
    "Shutdown",
    "ShutdownRequested",
    "SpeechEndpointDetected",
    "SpeechStopRequested",
    "Startup",
    "SynthesisStarted",
    "TranscriptReady",
    "WakeTriggered",
    "WatchdogTriggered",
]
