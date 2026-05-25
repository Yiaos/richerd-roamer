# Roamerd Command Reference

## Runtime

`roamerd` is a long-running async event-driven daemon. It does not expose individual CLI commands like the legacy `roamer` CLI. Instead, external callers interact through the ControlBridge Unix socket or the legacy compat shim.

## Entry Point

```bash
python -m roamerd --config config/roamerd.yaml
```

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--config` | `config/roamerd.yaml` | Path to YAML config |
| `--dry-run` | — | Validate config, print driver assignments, exit |
| `--log-level` | `info` | Log level |
| `--version` | — | Print version and exit |

### Dry-run output

```
dry-run ok
hearing=alsa
speech=alsa
vision=fswebcam
motion=ros2_nav
```

## ControlBridge Operations

The primary programmatic interface. Unix socket, JSON request/response envelopes.

### ping

Health check.

```json
→ {"op": "ping"}
← {"status": "ok", "result": {"pong": true}}
```

### status

Full runtime state snapshot (StateManager model dump).

```json
→ {"op": "status"}
← {"status": "ok", "result": {"state": "...", "playback_active": false, ...}}
```

### run

Request an action. Policy-gated: the PolicyEngine evaluates admission before dispatching.

```json
→ {"op": "run", "args": {"action": "speak", "payload": {"text": "你好"}}}
← {"status": "ok", "result": {"action_id": "...", "status": "accepted"}}
```

Wait modes:
- `wait: "accepted"` (default) — returns after policy admission
- `wait: "completed"` — waits for action terminal event or timeout

### session.start

Start a voice turn session (used by wake/converse flow).

```json
→ {"op": "session.start", "args": {"kind": "voice_turn"}}
← {"status": "ok", "result": {"session_id": "...", "kind": "voice_turn"}}
```

### action.status

Check status of a specific action by ID.

```json
→ {"op": "action.status", "args": {"action_id": "abc123"}}
← {"status": "ok", "result": {"action_id": "abc123", "status": "running", ...}}
```

### action.cancel

Cancel a running action.

```json
→ {"op": "action.cancel", "args": {"action_id": "abc123"}}
← {"status": "ok", "result": {"cancelled": true}}
```

### actions.list

List all tracked actions (running + recent terminal).

```json
→ {"op": "actions.list"}
← {"status": "ok", "result": {"actions": [...]}}
```

### Error response

```json
← {"status": "error", "error": {"code": "UNKNOWN_OP", "message": "..."}}
```

## Legacy CLI Compatibility

Old `roamer` commands still work when passed as trailing args:

```bash
python -m roamerd --config config/roamerd-pi.yaml watch --output /tmp/roamer.jpg
python -m roamerd --config config/roamerd-pi.yaml speak "你好" --style cheerful
python -m roamerd --config config/roamerd-pi.yaml listen --timeout 10 --text-only
python -m roamerd --config config/roamerd-pi.yaml sense --full
python -m roamerd --config config/roamerd-pi.yaml motion status
python -m roamerd --config config/roamerd-pi.yaml motion home --wait
```

The `roamer` console script entry point also routes through `roamerd.compat.legacy_cli`.

These are compatibility shims. New integrations should use the ControlBridge socket.

## Event Types (internal)

Key events flowing through the EventBus:

| Event | Source | Description |
|-------|--------|-------------|
| `system.module_ready` | app/modules | Module startup complete |
| `system.health_changed` | bridges/kernel | Component health state change |
| `system.watchdog_triggered` | supervisor | Stalled module detected |
| `hearing.wake_triggered` | HearingModule | Wake phrase detected |
| `hearing.transcript_ready` | HearingModule | STT result available |
| `speech.playback_started` | SpeechModule | TTS playback began |
| `speech.playback_finished` | SpeechModule | TTS playback ended |
| `vision.image_captured` | VisionModule | Camera frame captured |
| `motion.started` | MotionModule | Navigation began |
| `motion.completed` | MotionModule | Navigation finished |
| `motion.failed` | MotionModule | Navigation error |
| `cognition.request_needed` | PolicyEngine | LLM reasoning requested |
| `cognition.response_received` | CognitionBridge | LLM response arrived |
| `cognition.unavailable` | CognitionBridge | Circuit breaker open |
| `memory.candidate_raised` | various | Memory write candidate |
| `memory.flush_failed` | MemoryBridge | Flush to sink failed |
| `action.requested` | ActionManager | New action created |
| `action.completed` | ActionManager | Action finished successfully |
| `action.failed` | ActionManager | Action errored |

## Config Reference

Two standard configs:
- `config/roamerd.yaml` — development (mock drivers, local testing)
- `config/roamerd-pi.yaml` — production Pi (real hardware drivers)

See README.md for the full config structure.

## Testing

```bash
# Roamerd tests only
.venv/bin/python -m pytest tests/roamerd/ -q --tb=short

# All non-hardware
.venv/bin/python -m pytest -q -m 'not hardware' --tb=short

# Lint + type check
.venv/bin/ruff check src/roamerd/ tests/roamerd/
.venv/bin/mypy src/roamerd/ --strict
```
