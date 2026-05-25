# Roamer

Richerd's physical-body runtime. An event-driven async daemon (`roamerd`) that orchestrates perception, speech, motion, and cognition on a Raspberry Pi 5 mounted to a Roborock S5 base.

## Current Status

- `roamerd` is the active runtime (replaces the legacy `roamer` CLI)
- Capabilities: hearing (wake + STT), speech (TTS + playback), vision (camera), motion (ROS2/Valetudo), body status, reminders
- Bridges: ControlBridge (Unix socket), CognitionBridge (external LLM), MemoryBridge, TelegramBridge
- CI gates: ruff + mypy --strict + pytest (504 tests, non-hardware)
- Legacy `roamer` CLI commands route through `roamerd.compat.legacy_cli` shim

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      RoamerdApp                          │
├─────────────────────────────────────────────────────────┤
│  Kernel                                                 │
│  ├── EventBus (priority queues: high/normal/low)        │
│  ├── StateManager (runtime state + playback tracking)   │
│  ├── ActionManager (lifecycle, orphan scan, cleanup)    │
│  ├── PolicyEngine (intent matching, action admission)   │
│  ├── WorldModel (places, spatial context)               │
│  └── TraceLogger (structured observability)             │
├─────────────────────────────────────────────────────────┤
│  Capabilities (registered with Supervisor)              │
│  ├── HearingModule (wakeword + VAD + realtime STT)      │
│  ├── SpeechModule (TTS + playback + bluetooth)          │
│  ├── VisionModule (camera capture)                      │
│  ├── MotionModule (ROS2 nav driver)                     │
│  ├── BodyStatusModule (system health)                   │
│  └── ReminderModule                                     │
├─────────────────────────────────────────────────────────┤
│  Bridges (registered with Supervisor)                   │
│  ├── ControlBridgeServer (Unix socket, command router)  │
│  ├── CognitionBridge (circuit breaker, health events)   │
│  ├── MemoryBridge (buffered flush, failure tracking)    │
│  └── TelegramBridge                                     │
├─────────────────────────────────────────────────────────┤
│  Runtime                                                │
│  ├── Supervisor (module lifecycle management)           │
│  └── DriverRegistry (config-driven driver loading)      │
└─────────────────────────────────────────────────────────┘
```

All modules communicate through the EventBus. The kernel handles state, actions, policy, and observability. Capabilities produce/consume events for their domain. Bridges connect to external systems.

## Running

```bash
# Start the daemon
python -m roamerd --config config/roamerd.yaml

# Validate config without starting
python -m roamerd --config config/roamerd.yaml --dry-run

# Legacy CLI compatibility (routes through compat shim)
python -m roamerd --config config/roamerd.yaml speak "你好"
```

### Flags

- `--config` — Path to YAML config (default: `config/roamerd.yaml`)
- `--dry-run` — Validate config and print driver assignments, then exit
- `--log-level` — Log level (default: `info`)
- `--version` — Print version

### Signal Handling

- `SIGINT` / `SIGTERM` — Graceful shutdown (stops supervisor → action manager → event bus → observability)

## Control Interface

The ControlBridge exposes a Unix socket for external callers (OpenClaw, scripts, tools):

| Operation | Description |
|-----------|-------------|
| `ping` | Health check → `{pong: true}` |
| `status` | Full state snapshot |
| `run` | Request an action (policy-gated) |
| `session.start` | Start a voice turn session |
| `action.status` | Check action status by ID |
| `action.cancel` | Cancel a running action |
| `actions.list` | List all tracked actions |

Socket path is configured via `bridges.control.socket` in the config.

## Config Structure

Pydantic strict models, YAML-based. Key sections:

```yaml
runtime:
  state_dir: /run/roamer
  playback_stale_after_sec: 120.0
  supervisor:
    startup:
      connect_speaker_on_startup: false
      bluetooth_connect_retry_timeout_sec: 20.0

kernel:
  event_bus:
    high_maxsize: 1024
    handler_timeout_sec: 5.0

capabilities:
  hearing:
    wakeword: { driver: su03t_gpio, phrases: ["理查德"] }
    audio: { driver: alsa }
    vad: { driver: silero }
    stt: { provider: network_asr, url: "ws://..." }
  speech:
    tts: { primary: edge }
    playback: { driver: alsa }
    bluetooth: { driver: bluez, speaker_mac: "..." }
  vision:
    camera: { driver: fswebcam, device: /dev/video0 }
  motion:
    driver: ros2_nav

bridges:
  control: { enabled: true, socket: /run/roamer/control.sock }

policy:
  local_intents: [...]

world_model:
  places: [...]

ros2:
  valetudo_bridge: { host: "..." }

logging:
  level: INFO
  dir: logs
  max_bytes: 10485760
  backup_count: 10
  retention_days: 3
```

### Driver Registry

Drivers are loaded by category and name from config. Each category has a `mock` driver for testing:

| Category | Production | Mock |
|----------|-----------|------|
| wakeword | `su03t_gpio` | `mock` |
| audio_capture | `alsa` | `mock` |
| vad | `silero` | `mock` |
| realtime_stt | `network_asr` | `mock` |
| batch_asr | `funasr` | `mock` |
| tts | `edge`, `piper` | `mock` |
| playback | `alsa` | `mock` |
| bluetooth | `bluez` | `mock` |
| camera | `fswebcam` | `mock` |
| motion | `ros2_nav` | `mock`, `mock_ros2_nav` |

## Testing

```bash
# Roamerd unit tests
.venv/bin/python -m pytest tests/roamerd/ -q --tb=short

# All non-hardware tests
.venv/bin/python -m pytest -q -m 'not hardware' --tb=short

# Linting
.venv/bin/ruff check src/roamerd/ tests/roamerd/

# Type checking
.venv/bin/mypy src/roamerd/ --strict
```

## Hardware

- **Compute:** Raspberry Pi 5 8GB + 128G NVMe SSD
- **Base:** Roborock S5 (Valetudo firmware, persistent map)
- **Wake:** SU-03T voice recognition module (GPIO17, BCM17, pin 11)
- **Audio:** USB array mic (capture) + Bluetooth speaker (playback)
- **Camera:** USB webcam (fswebcam)

SU-03T wiring:

```
SU-03T VCC  → Pi 5V (pin 2/4)
SU-03T GND  → Pi GND (pin 6)
SU-03T OUT  → Pi GPIO17/BCM17 (pin 11)
```

## Installation

Production install on Pi:

- Repo: `/home/richerd/worksp/richerd-roamer`
- Virtualenv: `/home/richerd/.venv/roamer`
- Config: `config/roamerd-pi.yaml`
- Systemd: `roamerd.service`
- Runtime dir: `/run/roamer` (systemd-tmpfiles)
- Logs: `logs/`

## Legacy Compatibility

The old `roamer` CLI commands still work through the compat shim:

```bash
python -m roamerd --config config/roamerd.yaml watch --output /tmp/roamer.jpg
python -m roamerd --config config/roamerd.yaml speak "你好"
python -m roamerd --config config/roamerd.yaml motion status
```

The `roamer` console script entry point also routes through `roamerd.compat.legacy_cli`.

## Project Structure

```
src/roamerd/           # New runtime
  app.py               # App factory and wiring
  __main__.py          # Entry point
  kernel/              # EventBus, State, Actions, Policy, WorldModel, Observability
  capabilities/        # Hearing, Speech, Vision, Motion, BodyStatus, Reminder
  bridges/             # Control, Cognition, Memory, Telegram
  runtime/             # Supervisor, DriverRegistry
  config/              # Schema, loader
  contracts/           # Action, error, intent contracts
  compat/              # Legacy CLI shim, legacy config migration
  events/              # Typed event payload classes

src/roamer/            # Legacy (transitional, do not add new code here)

tests/roamerd/         # New test suite
migration/             # Phase A-E migration docs and checklists
config/                # YAML configs (roamerd.yaml, roamerd-pi.yaml)
scripts/               # Pi preflight, cutover, systemd helpers
```

## Docs

Project docs: `~/Documents/notes/2-Project/roamer/`

## License

MIT
