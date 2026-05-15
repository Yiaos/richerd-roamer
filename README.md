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
- `roamer motion goto --point <name> [--angle <deg>] [--wait]`
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
roamer motion goto --point 阳台 --wait
roamer motion goto --point 阳台 --angle 90 --wait
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
- runtime log: `logs/roamer.log`
- daemon: `roamer-serve.service`
- hands-free wake: `roamer-wake.service`

## roamerd Migration Status

The new body runtime lives under `src/roamerd/` and is intended to replace the
old command-centered orchestration during Phase E. `roamerd` is the long-lived
runtime; legacy CLI/socket entry points are transitional adapters that should
route through ControlBridge and PolicyEngine rather than calling the old
`wake -> converse -> speak` chain directly.

The draft cutover service is `systemd/roamerd.service`:

```text
python -m roamerd --config config/roamerd.yaml serve
```

Before replacing `roamer-serve.service` / `roamer-wake.service`, run
`scripts/roamerd-pi-preflight.sh` on the Pi and complete live acceptance for
SU-03T, ALSA, fswebcam, Bluetooth, ROS 2, Valetudo, OpenClaw, and network ASR.
Pi OS target for Phase E is Ubuntu 24.04, matching the ROS 2 Jazzy deb packages
used by the design. A Debian 13 Raspberry Pi OS install is not a passing Phase E
target unless the design is explicitly changed to a non-deb ROS2 installation
path.

Phase E operator sequence:

1. Back up current Pi config/secrets and hardware facts before any OS work:
   `config.yaml`, `/home/richerd/.config/roamer/env`, `/etc/roamer/roamer.env`,
   systemd unit/drop-in output, `arecord -l`, `aplay -l`, Bluetooth devices, and
   Tailscale status. The non-destructive helper is
   `scripts/roamerd-pi-collect-phase-e-facts.sh`.
2. Reimage or upgrade the Pi to Ubuntu 24.04 arm64, then install ROS 2 Jazzy.
   The guarded helper for dependency/bootstrap work after the OS is installed is
   `scripts/roamerd-pi-ubuntu24-bootstrap.sh`; it requires
   `ROAMER_BOOTSTRAP_CONFIRM_INSTALL=1`.
3. Verify ROS 2 with
   `source /opt/ros/jazzy/setup.bash && python3 -c "import rclpy"`.
4. Recreate `/home/richerd/.venv/roamer` and install
   `python -m pip install -e ".[dev,speech,gpio]"`.
5. Run `PYTHON=/home/richerd/.venv/roamer/bin/python bash scripts/roamerd-pi-preflight.sh`.
6. Only after preflight passes, run and record live SU-03T, ALSA, fswebcam,
   Bluetooth, ROS 2, Valetudo, OpenClaw, and network ASR acceptance. The current
   runner is `scripts/roamerd-pi-phase-e-acceptance.sh` and requires
   `ROAMER_ACCEPTANCE_CONFIRM_LIVE=1`. The current blocker is tracked in issue
   #21.

Remaining transitional adapters:

- `src/roamerd/compat/legacy_config.py` maps existing `config.yaml` values into
  typed `RoamerdConfig`.
- `src/roamerd/compat/legacy_actions.py` keeps migration-era action naming and
  command compatibility.
- Legacy leaf drivers remain where they preserve hardware I/O behavior:
  ALSA/FunASR listening, Edge/Piper/ALSA/BlueZ speech, fswebcam vision, and
  SU-03T/OpenWakeword wake detection.
- `src/roamerd/capabilities/reminder.py` is intentionally non-persistent and
  transitional until reminders are delegated to a higher-level task system.
- `bridges.control.compat.fallback_to_cli` remains a migration-only escape hatch
  and should be removed after Phase E.

Removal plan:

1. Land `roamerd` behind the draft service while old services remain installed.
2. Run the Pi preflight and live acceptance checklist from the design notes.
3. Switch systemd startup to `roamerd.service` and stop the old serve/wake
   services.
4. Keep the `roamer` CLI as a thin ControlBridge client for one migration
   window.
5. Remove compatibility-only adapters once no scripts depend on old action
   envelopes, detached reminders, or `fallback_to_cli`.

SU-03T wake wiring:

```text
SU-03T VCC  -> Raspberry Pi 5V, physical pin 2 or 4
SU-03T GND  -> Raspberry Pi GND, physical pin 6
SU-03T OUT  -> Raspberry Pi GPIO17 / BCM17, physical pin 11
```

Hardware wiring diagram:

```text
              Raspberry Pi GPIO header
              +------------------------------+
              | pin 2/4  5V  ---------------+--> SU-03T VCC
              | pin 6    GND ---------------+--> SU-03T GND
              | pin 11   GPIO17 / BCM17 <---+--- SU-03T OUT
              +------------------------------+

              SU-03T module
              +------------------------------+
              | VCC  input: use Pi 5V        |
              | GND  common ground           |
              | OUT  3.3V logic wake signal  |
              | 3V3  regulated output only   |
              +------------------------------+
```

`SU-03T 3V3` is the module's regulated 3.3V output, not the normal supply input
for this setup. Confirm the OUT pin is 3.3V logic before connecting it to GPIO17.

Streaming STT backend:

Roamer can use a LAN vLLM Qwen ASR backend for realtime STT while keeping
Silero as the local endpointing/turn-boundary layer. The configured backend is:

```yaml
converse:
  stt:
    mode: realtime_with_batch_fallback
    provider: vllm_realtime
    url: "ws://hurricane.tail33ee82.ts.net:8302/v1/realtime"
    model: "qwen3-asr-0.6b"
    fallback: batch
```

Before enabling hands-free tests, verify the backend from the Pi:

```bash
curl http://hurricane.tail33ee82.ts.net:8302/v1/models
```

The vLLM service must expose the model id `qwen3-asr-0.6b`. If the realtime
provider fails or times out, Roamer falls back to the existing FunASR batch path
when `fallback: batch` is configured.

Continuous wake conversation:

After a SU-03T wake hit, Roamer opens a short follow-up window so the user can
ask the next question without repeating the wake phrase. Local replies refresh
the window after playback. Discord fallback returns Roamer to idle while the
external reply is pending, then opens the follow-up window after `roamer speak`
finishes playback. Wake listening is skipped while playback is active so Roamer
does not record its own TTS.

```yaml
runtime:
  state_dir: /run/roamer
  playback_stale_after_sec: 120.0

converse:
  wakeword:
    followup_timeout_sec: 3.0
    continuous_followup_enabled: true
    max_followup_turns: 3
    stop_phrases: [不用了, 结束, 停止, 可以了]
```

The installer creates the shared `/run/roamer` runtime directory through
systemd-tmpfiles. Playback state uses one marker file per active `roamer speak`
under `playback.d/`, so overlapping playback cannot clear another process's
active marker. Roamer treats markers older than
`runtime.playback_stale_after_sec` as stale.

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
- installs Roamer with speech and GPIO dependencies
- points `/usr/local/bin/roamer` at the virtualenv entrypoint
- creates `logs` for structured runtime logs
- runs proxy discovery and keeps proxy values in `~/.config/roamer/env`
- writes `/etc/roamer/roamer.env` for systemd without exposing secrets in git
- installs drop-ins so `roamer-serve.service` runs as `richerd`, loads the env file, and can reach the user's PulseAudio session
- installs and starts `roamer-wake.service` when `converse.wakeword.driver` is `su03t_gpio`
- enables, restarts, and verifies the daemon

Post-install checks:

```bash
roamer serve ping
roamer serve status
roamer wake --once --timeout 30
roamer listen --timeout 1 --text-only
roamer converse --no-wakeword --no-sound --timeout 2 --max-turns 1
```

Runtime logs:

```bash
tail -f logs/roamer.log
find logs -maxdepth 1 -type f -name 'roamer.log*' -ls
```

Roamer writes JSONL runtime events for `serve`, `wake`, `listen`, `converse`, and
`speak`. Sensitive values such as tokens, passwords, proxy URLs, and authorization
fields are masked while keeping the first and last characters for debugging.
Logs rotate at 10 MB, keep up to 10 rotated files, and files older than 3 days
are deleted automatically.

`DISCORD_BOT_TOKEN` is required only for Discord fallback: local intents such as
time, status, position, and reminders run without Discord, but unmatched
conversation text is sent to Discord by the daemon.

## License

MIT
