# Capability Equivalence

This records the local mock-only equivalence surface for the roamerd cutover.

| Legacy capability | roamerd equivalent | Status |
| --- | --- | --- |
| wake/listen/STT | `HearingModule` with driver protocols and mock drivers | implemented |
| speech/TTS/playback | `SpeechModule` with TTS/playback/Bluetooth protocols and mock drivers | implemented |
| camera watch | `VisionModule` handling `watch` action lifecycle | implemented |
| sense/body status | `BodyStatusModule` preserving hostname/resource fields | implemented |
| reminder | `ReminderModule` using `ActionManager` speech actions | implemented |
| motion home/goto/stop | `MotionModule` with mock ROS2 and ROS2 contract driver | implemented |
| cognition | `CognitionBridge` transport from `cognition.request_needed` to response events | implemented |
| legacy CLI | `legacy_cli` maps legacy commands into ControlBridge `RequestEnvelope` | implemented |
| Unix socket protocol | `ControlBridgeServer` newline-delimited Node Protocol v1 | implemented |
| ControlBridge | protocol routing only; PolicyEngine and ActionManager own decisions/actions | implemented |

Non-goals in this local pass: real Pi hardware acceptance, real ROS2 `colcon build`, real Valetudo endpoint probe, and production Telegram/OpenClaw credentials.
