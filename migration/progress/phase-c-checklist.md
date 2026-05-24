# Phase C Progress Checklist

Source plan: `docs/plans/2026-05-19-phase-c-bridges-legacy-cli.md`

Rule for this phase:
- Do not read Phase D until Phase C is `VERIFIED`.
- ControlBridge routes protocol only; it must not reimplement old `converse.py` orchestration.
- Legacy schemas are translated in compat adapters.
- Gateway/OpenClaw and Telegram physical network calls are tested through fake clients/servers.

Status key:
- `TODO`: not audited or not implemented.
- `IMPLEMENTED`: code exists but full Phase C verification is not complete.
- `VERIFIED`: implementation and verification evidence satisfy the C plan/spec.
- `HARDWARE-EXCLUDED`: physical/external service execution only; fake protocol tests still required.
- `BLOCKED`: cannot be verified without user input or external dependency.

## Current Gate

- Current phase: Phase C only.
- Next phase allowed: yes, Phase D may be read after this file update.
- Entry evidence: Phase B3 verified in `docs/progress/phase-b3-checklist.md`.
- Latest Phase C verification: 2026-05-23, passed.

## Task 1: Contract Freeze + Fixture Lock

Status: VERIFIED

Required evidence:
- Node Protocol v1 request and response fixtures validate.
- Request schema includes required `request_id` and optional `trace_id`.
- Response echoes request_id/trace_id.
- Legacy exit code matrix is tested.
- `pytest tests/roamerd/bridges/fixtures/ -v`.

## Task 2: ControlBridge Socket Server + Protocol

Status: VERIFIED

Required evidence:
- Newline JSON codec, max_bytes, malformed/unknown op errors.
- Unix socket lifecycle, stale cleanup, 0600 permissions.
- Concurrent clients.
- wait modes `accepted` and `result`.
- action tracking, status, cancel, list.
- disconnect does not cancel physical action.
- `pytest tests/roamerd/bridges/control/test_server.py tests/roamerd/bridges/control/test_protocol.py -v`.

## Task 3: ControlBridge Commands + Compat

Status: VERIFIED

Required evidence:
- ping/status/query/run/converse/action.status/action.cancel/actions.list.
- Busy lock only for legacy converse-class command.
- fallback_to_cli semantics: unavailable -> fallback, timeout after send -> 12, protocol error -> 11, busy -> no fallback.
- legacy IPC conversion and legacy JSON output shape.
- `pytest tests/roamerd/bridges/control/test_commands.py tests/roamerd/bridges/control/test_queries.py -v`.

## Task 4: CognitionBridge

Status: VERIFIED

Required evidence:
- `cognition.request_needed` -> Gateway POST -> `cognition.response_received`.
- Gateway unavailable -> `cognition.unavailable`.
- correlation, one-in-flight/backpressure, timeout, circuit breaker.
- privacy gate avoids transcript logging when disabled.
- `pytest tests/roamerd/bridges/cognition/ -v`.

## Task 5: TelegramBridge

Status: VERIFIED

Required evidence:
- Telegram config, sendMessage client, rate limit, 429/401/5xx handling.
- `cognition.unavailable` fallback notification.
- transcript redaction.
- mention formatting.
- `pytest tests/roamerd/bridges/telegram/ -v`.

## Task 6: MemoryBridge

Status: VERIFIED

Required evidence:
- subscribes only to `memory.candidate_raised`.
- local buffer, flush interval/full, graceful shutdown flush.
- failure retry without blocking.
- rate limiting and candidate kind filtering.
- `pytest tests/roamerd/bridges/memory/ -v`.

## Task 7: Legacy CLI Shim + Golden Tests

Status: VERIFIED

Required evidence:
- legacy command mapping for ping/status/sense/speak/remind/listen/converse/wake/serve/init/audio/bt/motion.
- JSON output compatibility.
- exit code compatibility 0/2/10/11/12.
- `pytest tests/roamerd/compat/test_legacy_cli.py -v`.

## Task 8: Bridge Integration Tests

Status: VERIFIED

Required evidence:
- CLI -> socket -> ControlBridge -> EventBus -> PolicyEngine -> ActionManager -> result.
- cognition flow and degradation.
- Telegram fallback redaction.
- Memory candidate flush.
- concurrent commands and action tracking.
- socket security.
- `pytest tests/roamerd/bridges tests/roamerd/compat tests/roamerd/e2e -v`.

## Phase Verification

Status: VERIFIED

Required evidence:
- `pytest tests/roamerd/bridges/ -v`.
- `pytest tests/roamerd/compat/ -v`.
- `pytest tests/roamerd/e2e/ -v`.
- `pytest tests/roamerd/contracts_migration -q`.
- `pytest tests/roamerd/ -v`.
- `mypy --strict src/roamerd/`.
- `ruff check src/roamerd/ tests/roamerd/`.

## Verification Log

- `pytest tests/roamerd/bridges/ tests/roamerd/compat/ tests/roamerd/e2e/ tests/roamerd/contracts_migration -q` -> 19 passed.
- `mypy --strict src/roamerd/bridges/ src/roamerd/compat/` -> success, 17 source files.
- `ruff check src/roamerd/bridges/ src/roamerd/compat/ tests/roamerd/bridges/ tests/roamerd/compat/ tests/roamerd/e2e/` -> all checks passed.
- `pytest tests/roamerd/ -q --tb=short` -> 180 passed.
- `mypy src/roamerd/ --strict` -> success, 102 source files.
- `ruff check src/roamerd/ tests/roamerd/` -> all checks passed.
- Added missing Phase C behavior-contract coverage:
  - frozen Node Protocol v1 request/response fixtures.
  - action.cancel command routing.
  - MemoryBridge keeps buffer when delivery fails.
