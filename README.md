# Roamer

Richerd's physical-body CLI.

Roamer exposes action-based commands with deterministic JSON output so OpenClaw (or any caller) can invoke capabilities reliably.

## Current Status

- Phase 1 is active
- `watch` / `speak` / `sense` are usable
- `listen` exists but still under real-world tuning (audio device and VAD stability)
- `init` runs Roamer-owned startup initialization such as Bluetooth speaker connect
- `motion` is now available with Valetudo-backed base mobility (`status / position / locate / home / goto`)

## Implemented Commands

### Core capabilities

- `roamer watch` — visual perception (capture image)
- `roamer speak` — voice output (TTS, supports `--style`)
- `roamer listen` — voice input (record + VAD + ASR)
- `roamer sense` — self-state perception
- `roamer init` — startup initialization owned by Roamer itself
- `roamer motion status`
- `roamer motion position`
- `roamer motion locate`
- `roamer motion home [--wait]`
- `roamer motion goto --x <x> --y <y> [--angle <deg>] [--wait]`

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

# startup initialization (for systemd / boot hooks)
roamer init

# motion
roamer motion status
roamer motion position
roamer motion locate
roamer motion home --wait
roamer motion goto --x 25500 --y 25300 --wait
roamer motion goto --x 25500 --y 25300 --angle 90 --wait

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

## Config Resolution

- Default config path is **repo-local** `config.yaml` (project root)
- Use `-c/--config` for explicit override
- If repo `config.yaml` is absent and no `-c` is provided, Roamer falls back to internal defaults

## Startup & Initialization

Roamer should own its own initialization logic.

That means:
- systemd / boot hooks should start `roamer init`
- startup behavior (for example Bluetooth speaker connect) should live in Roamer config + code
- host-level shell scripts are only temporary migration tools, not the long-term architecture

Current behavior:
- `roamer init` can run boot-time initialization tasks
- if `init.connect_speaker_on_startup: true` and `bluetooth.speaker_mac` is configured,
  Roamer waits for the Bluetooth controller to become ready, then retries speaker connect during startup
- `roamer speak` still keeps lazy reconnect before playback as a runtime fallback

## Audio Troubleshooting (fallbacks, not prerequisites)

Normal flow should work without manual prep:
- `roamer init` can perform boot-time speaker connect with controller-ready wait + retry.
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

## Motion Test Safety

To prevent accidental real-hardware movement during unit tests:
- motion unit tests block real network calls by default
- tests must inject fake `urlopen` stubs/mocks for Valetudo driver calls
- accidental live HTTP calls fail fast in test runtime

## Architecture

```
CLI Layer (cli/)
    ↓
Platform Runtime (platform/)
    ↓
Domain Plugins (plugins/perception, plugins/interaction)
    ↓
Plugin-local Capabilities and Drivers
```

`domains/` stores semantic contracts only; implementations live in `plugins/`

Plugins expose actions through registry dispatch; command handlers stay thin and contract-focused.

## Docs

Project docs live in the knowledge base:

`~/Documents/notes/2-Project/roamer/`

(Repository `docs/` is symlinked to that location.)

## Installation

Roamer's production install on the Pi is expected to run from:

- repo: `/home/richerd/worksp/richerd-roamer`
- virtualenv: `/home/richerd/.venv/roamer`
- CLI symlink: `/usr/local/bin/roamer`
- runtime env: `/home/richerd/.config/roamer/env`
- systemd env: `/etc/roamer/roamer.env`
- daemon: `roamer-serve.service`

Create the runtime secret file before installing. Do not commit this file.

```bash
mkdir -p ~/.config/roamer
chmod 700 ~/.config/roamer
cat > ~/.config/roamer/env <<'EOF'
# Roamer runtime secrets. Do not commit.
export DISCORD_BOT_TOKEN=<discord bot token>
EOF
chmod 600 ~/.config/roamer/env
```

Run the installer from the Roamer repo on the Pi:

```bash
cd /home/richerd/worksp/richerd-roamer
./install.sh
```

The installer fails fast if required files or values are missing. It:

- verifies `config.yaml`, `systemd/roamer-serve.service`, `scripts/init-roamer-proxy.sh`, and `DISCORD_BOT_TOKEN`
- creates or reuses `/home/richerd/.venv/roamer`
- installs Roamer with speech dependencies
- points `/usr/local/bin/roamer` at the virtualenv entrypoint
- runs proxy discovery and keeps proxy values in `~/.config/roamer/env`
- writes `/etc/roamer/roamer.env` for systemd without exposing secrets in git
- installs drop-ins so `roamer-serve.service` runs as `richerd` and loads the env file
- enables, restarts, and verifies the daemon

Post-install checks:

```bash
roamer serve ping
roamer serve status
roamer listen --timeout 1 --text-only
roamer converse --no-wakeword --no-sound --timeout 2 --max-turns 1
```

`DISCORD_BOT_TOKEN` is required only for Discord fallback: local intents such as
time, status, position, and reminders run without Discord, but unmatched
conversation text is sent to Discord by the daemon.

## License

MIT
