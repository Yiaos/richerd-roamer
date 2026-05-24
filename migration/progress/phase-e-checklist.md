# Phase E Progress Checklist

Source plan: `docs/plans/2026-05-22-phase-e-cutover-legacy-removal.md`

Rule for this phase:
- Phase E is cutover/validation only; no new feature expansion.
- Physical Pi/systemd/24h execution can be `HARDWARE-EXCLUDED` in this workspace, but acceptance docs, scripts, config validation, compat tests, and no-dual-bind checks must exist.
- Legacy `src/roamer/` must be deleted or explicitly marked transitional/deprecated; do not claim it is gone while it remains.

Status key:
- `TODO`: not audited or not implemented.
- `IMPLEMENTED`: code/docs exist but full verification is not complete.
- `VERIFIED`: non-hardware implementation and verification satisfy the E plan/spec.
- `HARDWARE-EXCLUDED`: physical Pi/systemd/24h execution only.
- `BLOCKED`: cannot be verified without user input or external dependency.

## Current Gate

- Current phase: Phase E only.
- Next phase allowed: no.
- Entry evidence: Phase D non-hardware gates verified in `docs/progress/phase-d-checklist.md`.
- Latest Phase E verification: 2026-05-23, passed for non-hardware gates.

## Task 0: Acceptance Matrix Skeleton

Status: VERIFIED

Required evidence:
- `docs/phase-e-acceptance-matrix.md` exists and covers migration completion criteria, hidden contracts, verification command, evidence path, and pass/fail criteria.

## Task 1: Capability Audit Expanded

Status: VERIFIED

Required evidence:
- `docs/design/capability-equivalence.md` covers explicit capabilities and hidden user contracts.
- Any missing capability is marked blocker or intentional non-goal.

## Task 2: Config Migration + Validation

Status: VERIFIED

Required evidence:
- `config/roamerd.yaml` and `config/roamerd-pi.yaml`.
- legacy config leaf-key migration/deprecated coverage.
- dry-run validates resolved config/driver load plan without starting hardware.
- `pytest tests/roamerd/config -q`.

## Task 3: Runtime Entrypoint + Lifecycle

Status: VERIFIED

Required evidence:
- `python -m roamerd --dry-run`.
- `python -m roamerd --config config/roamerd.yaml` starts and exits cleanly on SIGTERM.
- runtime tests cover READY/DEGRADED/FATAL_CONFIG/shutdown.

## Task 4: CLI/IPC Compat Cutover

Status: VERIFIED

Required evidence:
- legacy shim routes to ControlBridge.
- no dual bind check script exists.
- compat tests pass.

## Task 5: Systemd + Pi Deployment

Status: HARDWARE-EXCLUDED

Required evidence:
- systemd/deploy artifacts exist.
- physical `systemctl start roamerd`, old service mask, device permissions are not claimed complete in this workspace.

## Task 6: Pi Acceptance

Status: HARDWARE-EXCLUDED

Required evidence:
- `migration/pi-acceptance-phase-e.md` exists with dated evidence placeholders.
- 24h stability is not claimed complete in this workspace.

## Task 7: Legacy Transition

Status: VERIFIED

Required evidence:
- `src/roamer/README.md` marks legacy tree transitional/deprecated.
- legacy adapter inventory/removal plan exists.
- old code is not described as removed unless actually removed.

## Phase Verification

Status: VERIFIED

Required evidence:
- `pytest tests/roamerd/runtime tests/roamerd/docs tests/roamerd/compat tests/roamerd/config tests/roamerd/contracts_migration -q`.
- `pytest tests/roamerd/ -q --tb=short`.
- `pytest -q -m 'not hardware' --tb=short`.
- `mypy --strict src/roamerd/`.
- `ruff check src/roamerd/ tests/roamerd/`.
- `python -m roamerd --dry-run`.
- `python -m roamerd --config config/roamerd.yaml` starts and exits cleanly on SIGTERM.

## Verification Log

- `pytest tests/roamerd/runtime tests/roamerd/docs tests/roamerd/compat tests/roamerd/config tests/roamerd/contracts_migration -q` -> 30 passed.
- `python -m roamerd --config config/roamerd.yaml --dry-run` -> dry-run ok, dev driver plan printed.
- `python -m roamerd --config config/roamerd-pi.yaml --dry-run` -> dry-run ok, `motion=ros2_nav`.
- `pytest tests/roamerd/ -q --tb=short` -> 208 passed.
- `pytest -q -m 'not hardware' --tb=short` -> 504 passed, 8 deselected.
- `mypy src/roamerd/ --strict` -> success, 103 source files.
- `ruff check src/roamerd/ tests/roamerd/` -> all checks passed.
- `python -m roamerd --config config/roamerd.yaml`, SIGTERM after startup -> stdout `roamerd started`, stderr empty, exit 0.
- `python -m roamerd --config <temp control config> ping` against enabled ControlBridge socket -> `pong: true`.
- PR review fixes verified: ControlBridge wait modes are `accepted`/`completed` with default `accepted`; completed wait returns terminal result or timeout/detach; ActionManager publishes real app session IDs; ActionStatus/PreemptionScope use contracts as the single source of truth; MotionModule no longer imports or type-checks mock drivers; CognitionBridge propagates correlation_id and serializes in-flight requests.
- Added/fixed Phase E non-hardware cutover artifacts:
  - `migration/pi-acceptance-phase-e.md` with HARDWARE-EXCLUDED Pi/24h evidence template.
  - `src/roamer/README.md` marks legacy tree TRANSITIONAL.
  - `config/roamerd-pi.yaml` now uses `motion.driver: ros2_nav`.
  - `src/roamer/cli/main.py` is a pure `roamerd.compat.legacy_cli` shim, and obsolete legacy `tests/cli` runtime/plugin assertions are excluded from pytest collection.
- Physical/systemd items not claimed complete: actual Pi systemctl cutover, old service masking on Pi, hardware permissions, real SU-03T/ALSA/fswebcam/Bluetooth/ROS2 motion acceptance, 24h stability.
