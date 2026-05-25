# Phase B3 Progress Checklist

Source plan: `docs/plans/2026-05-19-phase-b3-driver-parity-e2e.md`

Rule for this phase:
- Do not read Phase C until B3 is `VERIFIED`.
- Driver loading must use an explicit registry, not open-ended dynamic import.
- Motion mock must use MotionModule action lifecycle and must not call Valetudo/HTTP.
- B3 must distinguish no-match -> cognition from matched-but-unavailable -> local rejection/degraded response.

Status key:
- `TODO`: not audited or not implemented.
- `IMPLEMENTED`: code exists but full B3 verification is not complete.
- `VERIFIED`: implementation and verification evidence satisfy the B3 plan/spec.
- `HARDWARE-EXCLUDED`: physical device execution only; registry and fake tests still required.
- `BLOCKED`: cannot be verified without user input or external dependency.

## Current Gate

- Current phase: Phase B3 only.
- Next phase allowed: yes, Phase C may be read after this file update.
- Entry evidence: Phase B2 verified in `docs/progress/phase-b2-checklist.md`.
- Latest B3 verification: 2026-05-23, passed.

## Task 1: Driver Registry + Config-Driven Loading

Status: VERIFIED

Required evidence:
- Explicit registry maps category/name to driver classes.
- Registered drivers cover B1/B2/B3 mock and real boundaries.
- Unknown driver raises DriverNotFoundError.
- Config-driven mock/real switching test.
- `pytest tests/roamerd/runtime/test_driver_registry.py -v`.

## Task 2: Motion Module + Motion Intent Catalog

Status: VERIFIED

Required evidence:
- MotionDriver Protocol with goto/home/stop/status/position.
- MotionModule lifecycle for goto/home/cancel/stop.
- Mock ROS2 driver simulates success/failure/delay without Valetudo/HTTP.
- Motion local intents are config-driven and route without CognitionBridge.
- Emergency stop stops/preempts motion.
- `grep -R "valetudo\\|urllib\\|requests\\|httpx" src/roamerd/capabilities/motion/` returns empty.
- `pytest tests/roamerd/capabilities/motion/ -v`.

## Task 3: E2E Integration

Status: VERIFIED

Required evidence:
- wake -> STT -> no match -> cognition.request_needed -> mock cognition response -> speak -> playback completed.
- local motion intent "回充电" -> motion.home -> motion.completed without cognition.
- "停" safety path stops motion.
- reminder intent coexists and schedules acknowledgement.
- cognition unavailable: local intent still works, non-local gets degraded speech.
- realtime STT unavailable falls back to batch.
- playback active wake ignored.
- motion unavailable reject is distinct from no-match.
- final intent catalog composition has safety + reminder + motion with no conflicts.
- `pytest tests/roamerd/e2e/ -v`.

## Phase Verification

Status: VERIFIED

Required evidence:
- `pytest tests/roamerd/e2e/ -v`.
- `pytest tests/roamerd/ -v`.
- `pytest tests/roamerd/contracts_migration -q`.
- `mypy --strict src/roamerd/`.
- `ruff check src/roamerd/ tests/roamerd/`.
- Valetudo/HTTP grep returns empty for motion capability.

## Verification Log

- `pytest tests/roamerd/runtime/test_driver_registry.py tests/roamerd/capabilities/motion/ tests/roamerd/e2e/ tests/roamerd/contracts_migration -q` -> 17 passed.
- `mypy --strict src/roamerd/runtime/driver_registry.py src/roamerd/capabilities/motion/` -> success, 7 source files.
- `ruff check src/roamerd/runtime/driver_registry.py tests/roamerd/runtime/test_driver_registry.py tests/roamerd/e2e/test_degradation.py` -> all checks passed.
- `pytest tests/roamerd/ -q --tb=short` -> 177 passed.
- `mypy src/roamerd/ --strict` -> success, 102 source files.
- `ruff check src/roamerd/ tests/roamerd/` -> all checks passed.
- `rg -i "valetudo|urllib|requests|httpx|/api/v2/robot" src/roamerd/capabilities/motion/` -> no matches.
- Added missing B3 behavior-contract coverage:
  - Driver registry now includes all implemented B1/B2/B3 mock and real driver boundaries.
  - Registry config-driven loading for real driver boundaries.
  - Matched-but-unavailable motion intent rejects locally without routing to cognition.
