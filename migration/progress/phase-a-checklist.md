# Phase A Progress Checklist

Source plan: `docs/plans/2026-05-17-kernel-skeleton.md`

Rule for this rewrite:
- Do not read or execute the next phase plan until every Phase A task below is `VERIFIED`.
- Existing post-Phase-A files may remain in the worktree, but they do not count as Phase A evidence.
- Mock/fake backends only replace hardware I/O. They must not reduce non-hardware behavior.
- A task is not complete until its tests fail before the fix when practical, pass after the fix, and the listed verify commands pass.

Status key:
- `TODO`: not audited or not implemented.
- `IMPLEMENTED`: code exists but full Phase A verification is not complete.
- `VERIFIED`: implementation and verification evidence satisfy the Phase A plan/spec.
- `BLOCKED`: cannot be verified without user input or external dependency.

## Current Gate

- Current phase: Phase A only.
- Next phase allowed: yes, Phase B1 may be read after this file update.
- Latest full Phase A verification: 2026-05-23, passed.
- Known scope issue: this worktree already contains later-phase files under `capabilities/`, `bridges/`, `ros2_ws/`, and related tests. They are ignored for Phase A completion until Phase A is closed.

## Task 1: Project Scaffolding + Event Foundation

Status: VERIFIED

Required evidence:
- Event envelope instantiation and JSON serialization.
- Priority ordering.
- Typed payload models for canonical event types.
- Dotted lowercase `event_type` values.
- `privacy_level` and `retention_hint` fields.
- `roamerd` importable.
- `mypy src/roamerd/events/ --strict`.
- `pytest tests/roamerd/kernel/test_event_bus.py::TestEventFoundation -v` or equivalent focused event-foundation tests.

## Task 2: Config & Contracts

Status: VERIFIED

Required evidence:
- Pydantic config load/validation from YAML.
- Environment expansion and deep merge.
- Default mock config.
- ErrorCode, legacy error map, ActionResult, exception hierarchy.
- ExitCategory values match legacy behavior.
- `compat/legacy_config.py` maps current `config.yaml` with `unmapped_leaf_keys == []`.
- Canonical legacy migration projection covers wakeword/STT/Discord/motion/serve/proxy defaults.
- `pytest tests/roamerd/contracts/ tests/roamerd/config/ -v`.
- `mypy src/roamerd/config/ src/roamerd/contracts/ src/roamerd/compat/ --strict`.

## Task 3: EventBus

Status: VERIFIED

Required evidence:
- Priority dispatch, same-priority FIFO.
- Handler exception isolation.
- LOW/NORMAL overflow drop-oldest with `system.queue_overflow`.
- HIGH backpressure.
- CRITICAL publish never blocks.
- Pattern subscription and unsubscribe.
- Stop drains cleanly.
- Serial handler dispatch.
- Handler timeout emits `system.handler_timeout`.
- CRITICAL fast path interrupts long non-critical handler.
- Safety watchdog emits `system.watchdog_triggered`.
- `pytest tests/roamerd/kernel/test_event_bus.py -v`.

## Task 4: StateManager

Status: VERIFIED

Required evidence:
- Single-writer event updates for audio, motion, module health, bridge health.
- Immutable/deep snapshot behavior.
- Unknown events do not crash.
- Startup session id.
- Playback stale derivation.
- Cognition unavailable derivation.
- Runtime mode derivation.
- `pytest tests/roamerd/kernel/test_state_manager.py -v`.

## Task 5: ActionManager

Status: VERIFIED

Required evidence:
- Action lifecycle including `PENDING`, `WAITING_RESOURCE`, `RUNNING`, `RUNNING_DETACHED`, terminal states.
- Resource locking, resource `none` concurrency.
- Resource busy returns error without admission policy.
- Two-step cancel with timeout terminal behavior.
- Two-step preemption with module ack and timeout terminal behavior.
- `RUNNING_DETACHED` still occupies resource.
- Query APIs.
- `system.health_changed` cleans crashed module running actions.
- `pytest tests/roamerd/kernel/test_action_manager.py -v`.

## Task 6: WorldModel + Observability

Status: VERIFIED

Required evidence:
- People/place/scene/position/time models and query APIs from `06-world-model.md`.
- TTL expiry for people and scenes.
- Static places restore after restart.
- Cognition events cannot mutate grounded world state.
- JSONL trace logging with context managers.
- Redaction, rotation, retention cleanup.
- Safety flush.
- Handler timeout and queue overflow recorded.
- Duplicate event logging suppressed.
- Request id/correlation inheritance compatibility.
- `pytest tests/roamerd/kernel/test_world_model.py tests/roamerd/kernel/test_observability.py -v`.

## Task 7: PolicyEngine

Status: VERIFIED

Required evidence:
- Facade over `IntentMatcher`, `AdmissionController`, and `PolicyRuleStore`.
- Config-driven local intent matching, including legacy intent fixtures.
- No hardcoded non-config behavior except allowed predefined evaluators/parsers.
- Admission checks allowlist, resource availability, module health, cognition availability, quiet hours/resource busy where configured.
- Busy resource can produce preempt decision and call ActionManager preemption when policy decides so.
- Safety event preempts motion only.
- `hearing.wake_triggered` ignored while speaking.
- `control.command_received` and `cognition.response_received` routed through admission.
- `memory.policy_update` can change matching/admission behavior without code changes.
- Reject notification behavior.
- `pytest tests/roamerd/kernel/test_policy_engine.py -v`.

## Task 8: Assembly Layer

Status: VERIFIED

Required evidence:
- CapabilityModule and Bridge protocols.
- Supervisor start/stop/health loop/graceful shutdown.
- Individual module failure degrades without crashing app.
- `create_app(config)` assembles Phase A kernel correctly.
- `python -m roamerd --help`.
- `pytest tests/roamerd/test_app.py -v`.

## Task 9: Integration Verification

Status: VERIFIED

Required evidence:
- Voice Spine Proof: `hearing.transcript_ready -> PolicyEngine -> ActionManager -> mock SpeechModule -> action.completed -> StateManager/Observability`.
- Event flow proof: publish -> dispatch -> state update -> action lifecycle.
- Safety proof: emergency stop preempts motion and records observability event.
- Clean startup/shutdown with no pending task/resource leaks.
- `pytest tests/roamerd/test_integration.py -v`.
- `timeout 5 python -m roamerd --config config/roamerd.yaml` starts and exits cleanly on SIGTERM.
- `pytest tests/roamerd/ -v --tb=short`.
- `mypy src/roamerd/ --strict`.
- `ruff check src/roamerd/`.

## Verification Log

- `pytest tests/roamerd/kernel tests/roamerd/config tests/roamerd/contracts tests/roamerd/contracts_migration tests/roamerd/test_app.py tests/roamerd/test_integration.py tests/roamerd/test_main.py -q` -> 100 passed.
- `pytest tests/roamerd/ -q --tb=short` -> 147 passed.
- `mypy src/roamerd/ --strict` -> success, 92 source files.
- `ruff check src/roamerd/ tests/roamerd/` -> all checks passed.
- `python -m roamerd --help` -> usage output returned exit 0.
- `python -m roamerd --config config/roamerd.yaml`, SIGTERM after startup -> stdout `roamerd started`, stderr empty, exit 0.
- Added missing Phase A proof tests before verification:
  - ActionManager cancel timeout reaches `CANCELLED`.
  - ActionManager direct preemption timeout reaches `PREEMPTED`.
  - PolicyEngine routes `control.command_received`.
  - PolicyEngine applies `memory.policy_update`.
  - PolicyEngine preempts lower-priority busy resources.
  - PolicyEngine ignores wake while speaking and requests listen while idle.
  - Observability suppresses duplicate bus events by event id.
  - Supervisor health loop publishes degraded health without crashing.
  - Voice Spine Proof goes through mock SpeechModule and records `action.completed` in Observability.
