# Phase D Progress Checklist

Source plan: `docs/plans/2026-05-19-phase-d-ros2-substrate.md`

Rule for this phase:
- Do not read Phase E until Phase D is `VERIFIED` or physical Pi-only acceptance items are explicitly `HARDWARE-EXCLUDED`.
- roamerd must not import Valetudo/HTTP clients; Valetudo access belongs only in ROS 2 bridge package.
- Physical Pi/S5 execution can be excluded here, but contracts, ROS interface files, fake ROS/Valetudo tests, and grep gates are not excluded.

Status key:
- `TODO`: not audited or not implemented.
- `IMPLEMENTED`: code exists but full Phase D verification is not complete.
- `VERIFIED`: implementation and verification evidence satisfy the D plan/spec.
- `HARDWARE-EXCLUDED`: physical Pi/S5 execution only; non-hardware tests still required.
- `BLOCKED`: cannot be verified without user input or external dependency.

## Current Gate

- Current phase: Phase D only.
- Next phase allowed: yes, Phase E may be read after this file update.
- Entry evidence: Phase C verified in `docs/progress/phase-c-checklist.md`.
- Latest Phase D verification: 2026-05-23, passed for non-hardware gates.

## Task 0A: Valetudo Reality Probe

Status: HARDWARE-EXCLUDED

Required evidence:
- `docs/design/valetudo-reality-probe.md` records required endpoints and marks real request/response capture as Pi/S5 acceptance work.
- Physical Valetudo execution is excluded in this workspace.

## Task 0: Motion Contract Specification

Status: VERIFIED

Required evidence:
- `docs/design/motion-contract.md` defines coordinate frame, primitives, RobotState, stale rules, stop semantics, map invalidation, arrival tolerance, running-detached, error taxonomy, shutdown order.
- grep checks for required terms.

## Task 1: ROS 2 Interface Definitions

Status: VERIFIED

Required evidence:
- `roamer_interfaces` package exists.
- Stop.srv exists.
- RobotState includes map_id/map_hash.
- GoTo result does not contain success.
- GetCapabilities is absent.
- `colcon build --packages-select roamer_interfaces` if colcon is available; otherwise package file tests.

## Task 2: Valetudo Bridge Node

Status: VERIFIED

Required evidence:
- ROS bridge package contains Valetudo HTTP code only under `ros2_ws`.
- Bridge reports physical state/status, not semantic success.
- Fake Valetudo tests cover status/position/stop/goto/home.

## Task 3: Mock Nav Node

Status: VERIFIED

Required evidence:
- mock_nav_node provides same interface shape and configurable delay/failure.
- fake tests cover RobotState and GoTo/Home behavior.

## Task 4: MotionModule Ros2NavDriver

Status: VERIFIED

Required evidence:
- Ros2NavDriver has no Valetudo/urllib import.
- stale state rejects goto/home and allows stop.
- arrival tolerance is evaluated in roamerd side.
- running-detached/client timeout behavior is observable.
- `pytest tests/roamerd/capabilities/motion/test_ros2_nav.py -v`.

## Task 5: Place Registry

Status: VERIFIED

Required evidence:
- PlaceRegistry resolves/list/nearest/invalidate.
- map_id/map_hash invalidation marks places stale.
- Motion named place resolution remains in roamerd/WorldModel.

## Task 6: Integration and Pi Acceptance

Status: HARDWARE-EXCLUDED

Required evidence:
- non-hardware integration tests pass.
- Pi real goto/cancel/stop/bridge crash/Valetudo unreachable/map reset are listed as physical acceptance and not claimed complete.

## Phase Verification

Status: VERIFIED

Required evidence:
- `pytest tests/roamerd/capabilities/motion tests/roamerd/ros2 tests/roamerd/contracts_migration -q`.
- `mypy --strict src/roamerd/capabilities/motion`.
- `ruff check src/roamerd/capabilities/motion ros2_ws tests/roamerd/capabilities/motion tests/roamerd/ros2`.
- grep confirms no Valetudo/HTTP in `src/roamerd/capabilities/motion`.
- grep confirms GetCapabilities absent from interfaces.

## Verification Log

- `pytest tests/roamerd/capabilities/motion tests/roamerd/ros2 tests/roamerd/contracts_migration -q` -> 12 passed.
- `mypy --strict src/roamerd/capabilities/motion` -> success, 7 source files.
- `ruff check src/roamerd/capabilities/motion ros2_ws tests/roamerd/capabilities/motion tests/roamerd/ros2` -> all checks passed.
- `rg -i "valetudo|urllib|requests|httpx|/api/v2/robot" src/roamerd/capabilities/motion/` -> no matches.
- `rg "GetCapabilities" ros2_ws/src/roamer_interfaces/` -> no matches.
- `pytest tests/roamerd/ -q --tb=short` -> 202 passed.
- `mypy src/roamerd/ --strict` -> success, 103 source files.
- `ruff check src/roamerd/ tests/roamerd/` -> all checks passed.
- Added missing Phase D non-hardware gates:
  - `migration/motion-contract.md`.
  - `migration/valetudo-reality-probe.md` with HARDWARE-EXCLUDED physical capture status.
  - Home action and GetStatus/GetPosition/Locate services.
  - PlaceRegistry resolve/list/nearest/map invalidation.
- Hardware excluded items not claimed complete: real Pi/S5 goto, cancel during motion, stop during motion, bridge crash, Valetudo unreachable, map reset.
