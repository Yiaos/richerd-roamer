---
name: roamer-control
description: Operate and maintain Richerd's Roamer physical-body runtime (roamerd). Use when the user asks about Roamer capabilities, OpenClaw node operation, voice output/input, camera snapshots, body status, motion/navigation, or Roamer repository changes.
---

# Roamer Control

Roamer is Richerd's physical-body runtime (`roamerd`) and is paired as an OpenClaw node. It runs as a long-lived async event-driven daemon on a Raspberry Pi 5 mounted to a Roborock S5 base.

## First decision

- For **live operation**, prefer the OpenClaw `nodes` tool when Roamer is connected, because it is the first-class node path and avoids depending on SSH/MagicDNS from the host.
- If the `nodes` tool is unavailable or Roamer is disconnected as a node, fall back to `ssh -o BatchMode=yes -o ConnectTimeout=10 richerd@roamer '...'` from the host.
- For **repo work**, use `~/worksp/richerd-roamer`.
- For **project notes**, use `~/Documents/notes/2-Project/roamer/`.

## Architecture overview

```
roamerd (long-running async daemon)
├── Kernel: EventBus, StateManager, ActionManager, PolicyEngine, WorldModel, TraceLogger
├── Capabilities: Hearing, Speech, Vision, Motion, BodyStatus, Reminder
├── Bridges: Control (Unix socket), Cognition (LLM), Memory, Telegram
└── Runtime: Supervisor (lifecycle), DriverRegistry (config-driven)
```

All interaction goes through the EventBus. External callers use the ControlBridge Unix socket.

## OpenClaw node workflow

1. Check node presence with `nodes(action="status")` and confirm Roamer is `connected: true`.
2. Use `nodes(action="invoke", node="Roamer", invokeCommand="system.run", invokeParamsJson=...)` for live commands.
3. Keep commands explicit and bounded with reasonable timeouts.
4. Inspect both layers: node/tool success AND roamerd output fields.
5. If node invocation fails, fall back to SSH workflow.

Example node invocations:

```json
{"cmd":"python -m roamerd --config config/roamerd-pi.yaml --dry-run"}
{"cmd":"python -m roamerd --config config/roamerd-pi.yaml speak \"测试语音\""}
{"cmd":"python -m roamerd --config config/roamerd-pi.yaml motion status"}
{"cmd":"python -m roamerd --config config/roamerd-pi.yaml sense --full"}
```

Note: Legacy `roamer` CLI commands still work through the compat shim when passed as trailing args to `python -m roamerd`.

## ControlBridge operations

The primary programmatic interface is the Unix socket ControlBridge:

| Op | Description | Example payload |
|----|-------------|-----------------|
| `ping` | Health check | `{}` → `{pong: true}` |
| `status` | Full state snapshot | `{}` → state model |
| `run` | Request action (policy-gated) | `{action: "speak", payload: {text: "你好"}}` |
| `session.start` | Start voice turn | `{kind: "voice_turn"}` |
| `action.status` | Check action by ID | `{action_id: "..."}` |
| `action.cancel` | Cancel running action | `{action_id: "..."}` |
| `actions.list` | List tracked actions | `{}` |

Socket path: configured via `bridges.control.socket` (default: `/run/roamer/control.sock`).

## SSH fallback workflow

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 richerd@roamer 'cd /home/richerd/worksp/richerd-roamer && .venv/bin/python -m roamerd --config config/roamerd-pi.yaml speak "测试"'
ssh -o BatchMode=yes -o ConnectTimeout=10 richerd@roamer 'cd /home/richerd/worksp/richerd-roamer && .venv/bin/python -m roamerd --config config/roamerd-pi.yaml sense --full'
```

Gateway hostname rule: use `richer.tail33ee82.ts.net` for the host Gateway when configuring Roamer's node connection.

## Live-operation rules

- Treat `speak`, `motion home`, `motion goto`, and any action that produces sound or movement as real-world actions.
- If the user explicitly asks for the action, execute it; otherwise ask before producing sound or moving hardware.
- Before `motion goto`, check readiness with `status` unless the user is asking for emergency/obvious return-to-dock.
- Use timeouts on node/SSH commands; do not leave long-running hardware commands hanging.

## Capability map

Capabilities (roamerd modules):

- **Hearing** — wakeword detection (SU-03T GPIO), VAD (Silero), realtime STT (network ASR), batch ASR (FunASR)
- **Speech** — TTS (Edge/Piper), playback (ALSA), Bluetooth speaker management
- **Vision** — camera capture (fswebcam)
- **Motion** — ROS2 nav driver (Valetudo-backed S5 base mobility)
- **BodyStatus** — system health and self-state
- **Reminder** — scheduled reminders

Bridges:

- **Control** — Unix socket command interface for external callers
- **Cognition** — external LLM reasoning (circuit breaker protected)
- **Memory** — buffered memory sink with flush failure tracking
- **Telegram** — messaging bridge

## Development workflow

```bash
cd ~/worksp/richerd-roamer

# Run tests
.venv/bin/python -m pytest tests/roamerd/ -q --tb=short
.venv/bin/python -m pytest -q -m 'not hardware' --tb=short

# Lint + type check
.venv/bin/ruff check src/roamerd/ tests/roamerd/
.venv/bin/mypy src/roamerd/ --strict

# Dry-run validation
.venv/bin/python -m roamerd --config config/roamerd.yaml --dry-run
```

## Config

Config is Pydantic strict models loaded from YAML. Two configs:
- `config/roamerd.yaml` — development (mock drivers)
- `config/roamerd-pi.yaml` — production Pi (real drivers)

Key sections: `runtime`, `kernel`, `capabilities` (hearing/speech/vision/motion), `bridges`, `policy`, `world_model`, `ros2`, `logging`.

See `references/commands.md` for the full operation catalog.
