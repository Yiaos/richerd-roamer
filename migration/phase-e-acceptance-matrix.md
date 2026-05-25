# Phase E Acceptance Matrix

Status: FINAL for mock-only local cutover verification.

| Item | Owner | Verification | Evidence | Pass Criteria |
| --- | --- | --- | --- | --- |
| Full roamerd tests | codex | `pytest tests/roamerd -q` | test output | all pass |
| Migration contract | codex | `pytest tests/roamerd/contracts_migration -q` | test output | all pass |
| Type safety | codex | `mypy --strict src/roamerd` | mypy output | zero issues |
| Lint | codex | `ruff check src/roamerd tests/roamerd` | ruff output | zero issues |
| Dry run | codex | `python -m roamerd --config config/roamerd.yaml --dry-run` | stdout | driver plan printed |
| Runtime start/stop | codex | `python -m roamerd --config config/roamerd.yaml` then SIGTERM | process exit | exit 0 |
| Legacy safety | codex | grep/import tests | pytest output | no `roamerd` import of legacy orchestration |
| ROS2 mock substrate | codex | fake ROS2 tests | pytest output | stale state and stop semantics pass |
