# Phase B2 Progress Checklist

Source plan: `docs/plans/2026-05-19-phase-b2-vision-body-reminder.md`

Rule for this phase:
- Do not read Phase B3 until every non-hardware Phase B2 task below is `VERIFIED` or explicitly `HARDWARE-EXCLUDED`.
- B2 excludes detection, face recognition, VLM, and continuous perception by design.
- Physical camera/system hardware execution can be excluded, but subprocess boundaries, output contracts, timers, and state updates still need fake tests.

Status key:
- `TODO`: not audited or not implemented.
- `IMPLEMENTED`: code exists but full B2 verification is not complete.
- `VERIFIED`: implementation and verification evidence satisfy the B2 plan/spec.
- `HARDWARE-EXCLUDED`: physical device execution only; fake tests still required.
- `BLOCKED`: cannot be verified without user input or external dependency.

## Current Gate

- Current phase: Phase B2 only.
- Next phase allowed: yes, Phase B3 may be read after this file update.
- Entry evidence: Phase B1 verified in `docs/progress/phase-b1-checklist.md`.
- Latest B2 verification: 2026-05-23, passed.

## Task 1: Vision Module + fswebcam Driver

Status: VERIFIED

Required evidence:
- CameraDriver Protocol and CaptureResult.
- VisionModule subscribes to `action.started` for capture/watch action and does not make policy decisions.
- `vision.image_captured` event includes image path and dimensions.
- fswebcam subprocess driver with fake subprocess tests, output path, resolution, skip frames, and error handling.
- Physical camera execution is `HARDWARE-EXCLUDED`; fake subprocess tests are not excluded.
- `pytest tests/roamerd/capabilities/vision/ -v`.
- `mypy --strict src/roamerd/capabilities/vision/`.

## Task 2: Body Status

Status: VERIFIED

Required evidence:
- Body status output preserves legacy `sense` fields: hostname, uptime, cpu, memory, temperature, disk, network.
- Full hardware check mode surfaces ALSA, Bluetooth, camera, and Tailscale status.
- StateManager health updates via `system.health_changed`.
- `pytest tests/roamerd/capabilities/test_body_status.py -v`.

## Task 3: Reminder Transitional Module

Status: VERIFIED

Required evidence:
- `remind.schedule` is reached through PolicyEngine local intent/config catalog.
- ReminderModule schedules timers through action lifecycle.
- Due reminder requests speech through ActionManager, never SpeechModule directly.
- Immediate acknowledgement speak action.
- Cancel pending reminder by action/correlation id.
- Non-persistent restart behavior.
- `pytest tests/roamerd/capabilities/test_reminder.py -v`.

## Task 4: B2 Integration

Status: VERIFIED

Required evidence:
- Capture action -> VisionModule -> `vision.image_captured`.
- Body status query returns complete field set.
- Transcript reminder intent -> PolicyEngine -> ReminderModule -> timer -> speak action.
- `pytest tests/roamerd/capabilities/test_b2_integration.py -v`.

## Phase Verification

Status: VERIFIED

Required evidence:
- `pytest tests/roamerd/capabilities/vision/ tests/roamerd/capabilities/test_body_status.py tests/roamerd/capabilities/test_reminder.py -v`.
- `pytest tests/roamerd/capabilities/test_b2_integration.py -v`.
- `pytest tests/roamerd/contracts_migration -q`.
- `mypy --strict src/roamerd/capabilities/vision/ src/roamerd/capabilities/body_status.py src/roamerd/capabilities/reminder.py`.
- `ruff check src/roamerd/capabilities/ tests/roamerd/capabilities/`.

## Verification Log

- `pytest tests/roamerd/capabilities/vision/ tests/roamerd/capabilities/test_body_status.py tests/roamerd/capabilities/test_reminder.py tests/roamerd/capabilities/test_b2_integration.py tests/roamerd/contracts_migration -q` -> 11 passed.
- `mypy --strict src/roamerd/capabilities/vision/ src/roamerd/capabilities/body_status.py src/roamerd/capabilities/reminder.py` -> success, 8 source files.
- `ruff check src/roamerd/capabilities/vision/ src/roamerd/capabilities/body_status.py src/roamerd/capabilities/reminder.py tests/roamerd/capabilities/vision/ tests/roamerd/capabilities/test_body_status.py tests/roamerd/capabilities/test_reminder.py tests/roamerd/capabilities/test_b2_integration.py` -> all checks passed.
- `pytest tests/roamerd/ -q --tb=short` -> 174 passed.
- `mypy src/roamerd/ --strict` -> success, 102 source files.
- `ruff check src/roamerd/ tests/roamerd/` -> all checks passed.
- Added missing B2 behavior-contract coverage:
  - fswebcam subprocess boundary and camera error handling.
  - body.status hardware check field set in legacy-shaped result.
  - reminder cancel prevents due speak action.
  - reminder non-persistence across module restart.
