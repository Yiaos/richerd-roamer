# Roamer Doctor Runtime Acceptance Spec

Date: 2026-05-09
Status: Draft for review
Related issue: #16

## Objective

Add a deterministic Pi-side acceptance surface for Roamer so one command can answer:

> Is this body/runtime healthy enough to continue embodiment work?

Preferred operator-facing command:

```bash
roamer doctor
```

The first version should be narrow, read-mostly, and optimized for real weekend bring-up on Pi rather than architectural completeness.

## Why now

Roamer's current blocker is not another abstract capability. It is repeatable validation of the embodied runtime path on the real Pi:

- serve daemon reachable
- audio device present and stable
- STT backend reachable
- listen path working on the real array mic
- wake prerequisites healthy enough for later live tests
- motion provider reachable enough to trust future validation

Today this acceptance ritual is spread across README, status notes, and ad hoc checklists. That is expensive, easy to forget, and hard to automate.

`roamer doctor` should become the single deterministic entry point.

## Non-goals for v1

The first cut should **not**:

- move the robot by default
- require a full live wake conversation
- validate named-point correctness by driving anywhere
- depend on future `roamerd` runtime extraction being complete
- hide low-level failures behind prose-only summaries

## User-facing contract

### Command forms

```bash
roamer doctor
roamer doctor --json
roamer doctor --pretty
```

Optional later flags, not required for v1:

```bash
roamer doctor --include-listen-live
roamer doctor --include-wake-live
roamer doctor --include-motion-live
```

Default output should stay machine-friendly JSON, matching the repo's broader deterministic CLI contract.

## Output contract

Rough shape:

```json
{
  "ok": false,
  "host": "roamer-pi",
  "checked_at": "2026-05-09T21:00:00+08:00",
  "summary": {
    "passed": 4,
    "failed": 2,
    "warn": 1
  },
  "checks": {
    "serve_ping": {
      "ok": true
    },
    "serve_status": {
      "ok": true,
      "daemon": "running"
    },
    "audio_capture_device": {
      "ok": false,
      "expected": "hw:2,0",
      "found": ["hw:1,0"],
      "severity": "error"
    },
    "stt_backend": {
      "ok": true,
      "endpoint": "http://.../v1/models",
      "model": "qwen3-asr-0.6b"
    },
    "listen_smoke": {
      "ok": true,
      "latency_ms": 1430,
      "transcript_present": true
    },
    "wake_prereqs": {
      "ok": true,
      "gpio": "ready",
      "playback_state_dir": "/run/roamer"
    },
    "motion_baseline": {
      "ok": true,
      "provider": "valetudo",
      "reachable": true
    }
  }
}
```

### Severity model

Each check should surface one of:

- `ok`
- `warn`
- `error`
- `skipped`

Top-level `ok=true` only when no `error` checks exist.

## v1 checks

### 1. Serve health

Purpose: confirm the control plane is alive before deeper body checks.

Checks:

- `roamer serve ping`
- `roamer serve status`

Expected result:

- daemon reachable
- structured status payload parseable

Failure examples:

- service not running
- socket missing
- ping timeout
- malformed status output

## 2. Audio device presence

Purpose: detect the most common embodied failure early.

Checks:

- enumerate ALSA capture/playback devices
- resolve configured capture device from config
- verify configured capture device exists

Expected result:

- configured capture device, currently `hw:2,0`, is present
- playback side is at least enumerable

Failure classes should be distinguished:

- config missing
- configured device absent
- ALSA enumeration failed

## 3. STT backend reachability

Purpose: verify the realtime ASR path before blaming listen/wake logic.

Checks:

- inspect configured STT endpoint/model
- probe configured endpoint reachability
- when applicable, verify target model id is present

Expected result:

- endpoint responds
- expected model is visible or equivalent backend-specific readiness is confirmed

This check is network/backend validation only; it does not replace microphone smoke.

## 4. Listen smoke

Purpose: validate the capture → VAD → ASR path on the real machine.

v1 should keep this bounded and deterministic:

- short timeout
- text-only or debug-oriented path
- no long interactive loop

Suggested behavior:

- run a very short listen probe
- record whether audio capture worked
- record whether ASR returned anything or timed out cleanly
- return structured metadata such as latency, transcript_present, and failure reason

Important: a clean timeout due to silence should not be collapsed into the same bucket as device failure.

## 5. Wake prerequisites

Purpose: verify wake can be meaningfully tested later, without forcing a full live wake interaction in v1.

Checks:

- wake-related config present
- GPIO prerequisite readable
- playback-state path or equivalent wake dependency available
- required helper binaries/interfaces available

This should answer:

- can wake be tested now?
- if not, is the problem config, GPIO, binary, or runtime dependency?

## 6. Motion baseline

Purpose: check mobility dependencies without surprise movement.

Default v1 should be read-only:

- provider/config presence
- motion status/provider reachability
- optional position query if read-only and safe

Must not call `home` or `goto` by default.

## Named-point trust check follow-up

Once `motion.named_points` becomes executable surface, `roamer doctor` should add a **read-only named-point safety check**.

This check should not claim semantic correctness. It should only surface trust state such as:

- config declares named points
- verification evidence exists in `docs/valetudo-locations.md`
- configured point missing evidence
- evidence/config drift known

Possible result states:

- `verified`
- `configured-but-unverified`
- `docs-missing`
- `drift-known`

This is a trust-surface check, not a navigation correctness engine.

## Implementation constraints

- Keep CLI handler thin.
- Reuse existing capabilities/drivers where practical.
- Return deterministic JSON.
- Do not silently perform real-world actions.
- Separate infra missing vs hardware unavailable vs behavioral regression.
- Make failures legible enough for both humans and later orchestration.

## Suggested internal shape

One practical structure:

- `src/roamer/cli/commands/doctor.py` or equivalent thin entry
- small checker modules per concern:
  - serve
  - audio
  - stt
  - listen
  - wake
  - motion
- shared result schema for `ok/warn/error/skipped`

If the repo later extracts more runtime into `roamerd`, the command contract should stay stable while implementations move behind it.

## Acceptance criteria for v1

- `roamer doctor` exists and returns parseable deterministic JSON.
- It runs on Pi without requiring manual movement approval.
- It clearly reports pass/fail for:
  - serve health
  - audio capture device presence
  - STT backend reachability
  - listen smoke
  - wake prerequisites
  - motion baseline
- It distinguishes silent timeout from capture/config failure in listen smoke.
- It does not perform `motion home` / `motion goto` by default.
- README and weekend bring-up docs can point to `roamer doctor` as the first runtime acceptance step.

## Verification plan

Minimum verification before calling the command ready:

1. unit tests for per-check result normalization
2. unit tests proving motion checks are read-only by default
3. tests for failure-shape stability in JSON output
4. one Pi-side real run capturing at least:
   - healthy path example
   - one intentionally degraded path example (for example wrong capture device)

## Rollout suggestion

1. land command with serve/audio/stt/motion-readonly checks first
2. add bounded listen smoke
3. add wake prerequisite check
4. later add optional live flags and named-point trust check

This keeps the first useful slice small while still solving the current operational gap.
