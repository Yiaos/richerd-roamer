# Spec: Roamer Domain Plugin Architecture (Simplified)

## Objective
Keep one root package (`src/roamer`) and a clear separation of responsibilities:
- thin CLI
- platform primitives
- domain contracts
- domain plugins

No `shared` layer.

## Confirmed Decisions
1. Keep single package root: `roamer`.
2. Keep CLI command name: `roamer`.
3. Keep domain semantics in `domains/*` and implementations in `plugins/*`.
4. Keep drivers inside each plugin (`plugins/<domain>/drivers`).
5. If multiple actions reuse the same integration, reuse inside the same plugin first.

## Project Structure
```text
src/
  roamer/
    cli/
      main.py

    platform/
      config.py
      contract.py
      output.py
      errors.py
      plugin_registry.py
      runtime.py

    domains/
      perception/contracts.py
      interaction/contracts.py
      locomotion/contracts.py
      behavior/contracts.py

    plugins/
      perception/
        plugin.py
        actions/
        drivers/
      interaction/
        plugin.py
        actions/
        capabilities/
        drivers/
```

## Layer Rules
- `roamer.cli`: parse args, call runtime, emit deterministic contract output.
- `roamer.platform`: common runtime/config/contract primitives.
- `roamer.domains`: semantic contracts only; no hardware implementation.
- `roamer.plugins.<domain>`: executable actions, drivers, and domain orchestration.

## Contract Requirements
- Default command output is deterministic JSON.
- Error payloads include canonical `error_code`.
- Exit code mapping is stable via platform contract category mapping.

## Testing Strategy
- `tests/core/`: runtime/registry primitives.
- `tests/platform/`: contract/config/output behavior.
- `tests/plugins/interaction/`: interaction actions/drivers.
- `tests/plugins/perception/`: perception actions/drivers.
- `tests/cli/`: command contract and CLI behavior.
- CI baseline: `pytest -m 'not hardware'`.

## Success Criteria
1. `roamer` entrypoint resolves to `roamer.cli.main:main`.
2. Source and tests import only `roamer.*` active modules (no `shared`).
3. CLI contract regression remains green.
4. Plugin registration avoids eager initialization of unrelated actions.
