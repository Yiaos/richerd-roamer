# Roamer

Richerd's physical-body CLI.

Roamer exposes action-based commands with deterministic JSON output so OpenClaw (or any caller) can invoke capabilities reliably.

## Current Status

- Phase 1 is active
- `watch` / `speak` / `sense` are usable
- `listen` exists but still under real-world tuning (audio device and VAD stability)
- Motion control via Valetudo is planned next

## Implemented Commands

### Core capabilities

- `roamer watch` — visual perception (capture image)
- `roamer speak` — voice output (TTS, supports `--style`)
- `roamer listen` — voice input (record + VAD + ASR)
- `roamer sense` — self-state perception

### Utility commands

- `roamer audio record`
- `roamer audio play`
- `roamer bt status`
- `roamer bt connect`

## Usage

```bash
# visual
roamer watch --output /tmp/roamer.jpg

# voice output (legacy positional mode)
roamer speak "你好，Richer" --style cheerful

# voice input (default JSON output)
roamer listen --timeout 10 --debug

# two-command voice flow (recommended)
roamer listen --timeout 10 --text-only | roamer speak --stdin --prefix "我听到的是："

# equivalent variable style
TEXT=$(roamer listen --timeout 10 --text-only)
roamer speak "我听到的是：${TEXT:-我这次没有听清楚内容。}"

# self status
roamer sense --full

# audio utils
roamer audio record --duration 5 --output /tmp/rec.wav
roamer audio play /tmp/rec.wav

# bluetooth utils (manual fallback)
roamer bt status
roamer bt connect B8:5C:EE:89:00:BE
```

## Output Contract

Default behavior: commands return JSON.

Exception:
- `roamer listen --text-only` outputs plain text only (for shell pipelines)

Success example:

```json
{"ok": true, "path": "/tmp/roamer.jpg", "width": 1280, "height": 720}
```

Error example:

```json
{"ok": false, "error": "camera_not_found", "message": "No camera at /dev/video0"}
```

## Audio Troubleshooting (fallbacks, not prerequisites)

Normal flow should work without manual prep:
- `speak` already tries lazy Bluetooth reconnection internally.
- `listen` should run without requiring a `pulseaudio --kill` pre-step.

Use manual commands only when troubleshooting real device contention:
- If Bluetooth sink is missing: `roamer bt connect <MAC>`
- If capture device is blocked by PulseAudio on your setup: `pulseaudio --kill` and retry

## What "motion" Means

`motion` is **base mobility capability** (robot movement abstraction), not generic behavior orchestration.

For Roamer's near-term MVP, `motion` means Valetudo-backed base actions:
- `status`
- `position` (current x/y/angle when available)
- `home` (return to dock)
- `locate`
- `goto` (guarded by map readiness)

It explicitly does **not** mean full teleop/path planning/NL navigation in the first iteration.

## Architecture

```
CLI Layer (cli.py)
    ↓
Capability Layer (capabilities/)
    ↓
Driver Layer (drivers/)
```

Drivers are swappable via configuration.

## Docs

Project docs live in the knowledge base:

`~/Documents/notes/2-Project/roamer/`

(Repository `docs/` is symlinked to that location.)

## Installation

```bash
pip install -e ".[dev,speech]"
```

## License

MIT
