# Phase E Pi Acceptance

Status: HARDWARE-EXCLUDED in this local workspace. This document is the evidence template for the Pi 5 cutover run.

## Operator gate (2026-08-13)

Heartbeat check found:

- Pi `roamer` is offline (Tailscale ping/SSH timeout).
- The earlier off-device copy under `/tmp/roamerd-phase-e-backups/` is gone (`/tmp` is not durable).
- Issue #21 remains the only open software/hardware gate: choose Ubuntu 24.04 + ROS 2 Jazzy, or revise design for Debian 13.

Before any destructive OS work:

1. Power Pi and confirm SSH.
2. Re-run `scripts/roamerd-pi-collect-phase-e-facts.sh` on the Pi if the on-device backup is missing.
3. Pull off-device with `scripts/roamerd-phase-e-backup-pull.sh` into `~/Backups/roamer/phase-e/` (never `/tmp`).
4. Explicitly choose issue #21 path A (reimage Ubuntu 24.04) or path B (Debian 13 + non-deb ROS2 redesign).

## Happy Path

| Check | Status | Evidence |
| --- | --- | --- |
| `python -m roamerd --config config/roamerd-pi.yaml` reaches READY | pending Pi | dated log |
| SU-03T wake -> transcript -> cognition -> speech | pending Pi | event trace |
| motion.goto(point) via ROS 2 -> robot arrives | pending Pi | ROS/action log |
| motion.home() docks robot | pending Pi | ROS/action log |
| camera capture returns file | pending Pi | file path/log |
| body status returns hardware data | pending Pi | JSON output |
| legacy `roamer` shim routes to ControlBridge | pending Pi | command output |

## Degradation

| Check | Status | Evidence |
| --- | --- | --- |
| cognition unavailable -> local intent still works | pending Pi | event trace |
| realtime STT unavailable -> batch fallback/degraded result | pending Pi | event trace |
| ROS 2 unavailable -> motion rejects, other modules continue | pending Pi | health log |
| Bluetooth unavailable -> speech partial-success/fallback | pending Pi | action result |
| playback active -> wake ignored unless follow-up permits | pending Pi | event trace |
| bridge crash -> DEGRADED_READY and restart recovery | pending Pi | journal |

## 24h Stability

Required evidence: 24h journal window, RSS < 200MB without growth trend, no roamerd restarts, no queue overflow, no unexpected NOT_READY state, valid JSONL logs with request_id/correlation_id/action_id.

This workspace does not claim the 24h stability run complete.
