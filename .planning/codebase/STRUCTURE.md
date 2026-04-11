# Codebase Structure

**Analysis Date:** 2026-04-11

## Directory Layout

```text
[project-root]/
├── src/                     # Python package source (runtime code)
│   └── roamer/              # Core package
│       ├── cli.py           # CLI command entry and routing
│       ├── capabilities/    # Capability orchestration layer
│       ├── drivers/         # Driver interfaces, implementations, and registry
│       ├── config.py        # Config defaults + merge/load helpers
│       ├── output.py        # Standard success/error payload helpers
│       └── errors.py        # Domain exception types
├── tests/                   # Pytest suite (unit + hardware-marked tests)
├── .planning/codebase/      # Generated codebase mapping docs
├── pyproject.toml           # Packaging, scripts, lint/test tool config
├── pytest.ini               # Pytest discovery/marker config
├── config.example.yaml      # Example runtime configuration file
└── README.md                # Usage and high-level architecture notes
```

## Directory Purposes

**`src/roamer/`:**
- Purpose: Own all production runtime code.
- Contains: CLI adapters, capability orchestrators, driver abstractions/implementations, config/output/error primitives.
- Key files: `src/roamer/cli.py`, `src/roamer/config.py`, `src/roamer/output.py`, `src/roamer/errors.py`

**`src/roamer/capabilities/`:**
- Purpose: Implement user-facing operations that coordinate one or more drivers.
- Contains: `Capability` base class, concrete capability classes, and `_audio.py` utility capability wrapper.
- Key files: `src/roamer/capabilities/base.py`, `src/roamer/capabilities/watch.py`, `src/roamer/capabilities/speak.py`, `src/roamer/capabilities/listen.py`, `src/roamer/capabilities/sense.py`, `src/roamer/capabilities/_audio.py`

**`src/roamer/drivers/`:**
- Purpose: Isolate hardware/backend integrations and expose a registry-based plugin model.
- Contains: Domain subpackages (`audio/`, `camera/`, `bluetooth/`, `speech/`), registry, package init wiring.
- Key files: `src/roamer/drivers/registry.py`, `src/roamer/drivers/__init__.py`, `src/roamer/drivers/audio/base.py`, `src/roamer/drivers/audio/alsa.py`, `src/roamer/drivers/camera/fswebcam.py`, `src/roamer/drivers/bluetooth/bluez.py`, `src/roamer/drivers/speech/`

**`src/roamer/drivers/speech/`:**
- Purpose: Speech-domain integrations split by function.
- Contains: `asr/`, `tts/`, and `vad/` subpackages, each with `base.py`, concrete implementation(s), and `__init__.py`.
- Key files: `src/roamer/drivers/speech/asr/funasr.py`, `src/roamer/drivers/speech/tts/piper.py`, `src/roamer/drivers/speech/tts/edge.py`, `src/roamer/drivers/speech/vad/silero.py`

**`tests/`:**
- Purpose: Validate command behavior, config/output helpers, and driver behavior.
- Contains: Flat `test_*.py` modules plus shared fixture file.
- Key files: `tests/conftest.py`, `tests/test_cli_audio_flow.py`, `tests/test_audio.py`, `tests/test_watch.py`, `tests/test_tts.py`, `tests/test_asr.py`, `tests/test_vad.py`, `tests/test_sense.py`, `tests/test_config.py`, `tests/test_output.py`, `tests/test_bluetooth.py`

**`.planning/codebase/`:**
- Purpose: Persist generated mapping docs consumed by GSD planner/executor commands.
- Contains: Focus-specific markdown documents.
- Key files: `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md`, `.planning/codebase/STACK.md`, `.planning/codebase/INTEGRATIONS.md`, `.planning/codebase/CONVENTIONS.md`, `.planning/codebase/TESTING.md`, `.planning/codebase/CONCERNS.md`

## Key File Locations

**Entry Points:**
- `pyproject.toml`: Declares console script `roamer = "roamer.cli:main"`.
- `src/roamer/cli.py`: Click CLI root group and all command handlers.

**Configuration:**
- `src/roamer/config.py`: Default config map and deep merge loader.
- `config.example.yaml`: Canonical user-editable config shape and driver selection examples.
- `pytest.ini`: Pytest testpaths/marker declaration.

**Core Logic:**
- `src/roamer/capabilities/`: Runtime orchestration layer for commands.
- `src/roamer/drivers/registry.py`: Driver lookup and instantiation boundary.
- `src/roamer/drivers/`: Integration implementations and interface contracts.

**Testing:**
- `tests/`: All test modules are centralized at repo root test directory.
- `tests/conftest.py`: Shared fixture setup and marker registration.

## Naming Conventions

**Files:**
- Use `snake_case.py` module naming throughout source and tests (`src/roamer/config.py`, `tests/test_cli_audio_flow.py`).
- Use `base.py` for abstract interface definitions within each domain (`src/roamer/drivers/audio/base.py`, `src/roamer/capabilities/base.py`).
- Use implementation-specific driver filenames matching backend/tool names (`src/roamer/drivers/camera/fswebcam.py`, `src/roamer/drivers/speech/tts/piper.py`).

**Directories:**
- Use lowercase domain-based directories for bounded contexts (`src/roamer/capabilities/`, `src/roamer/drivers/bluetooth/`, `src/roamer/drivers/speech/vad/`).
- Keep speech subdomains nested under one parent (`src/roamer/drivers/speech/asr/`, `src/roamer/drivers/speech/tts/`, `src/roamer/drivers/speech/vad/`).

## Where to Add New Code

**New Feature:**
- Primary code: Add/extend capability modules in `src/roamer/capabilities/` and wire command surface in `src/roamer/cli.py`.
- Tests: Add corresponding `tests/test_<feature>.py` in `tests/`; include CLI invocation tests when behavior is user-facing.

**New Component/Module:**
- Implementation: For new backend integrations, add interface-conformant driver module under the matching domain in `src/roamer/drivers/` (for example `src/roamer/drivers/audio/<new_driver>.py`), register it with `register_driver(...)`, and expose import in domain `__init__.py`.

**Utilities:**
- Shared helpers: Put cross-domain helpers in `src/roamer/config.py`, `src/roamer/output.py`, or a new `src/roamer/<helper>.py` module if they do not belong to a single capability/driver domain.

## Special Directories

**`.planning/codebase/`:**
- Purpose: Generated architecture/stack/convention/testing/concern reference docs.
- Generated: Yes
- Committed: Yes

**`docs` (symlink):**
- Purpose: Link to external project knowledge base path referenced by `README.md`.
- Generated: No (symlink maintained manually)
- Committed: Yes (as symlink entry)

**`__pycache__/` (under `src/` and `tests/`):**
- Purpose: Python bytecode cache directories created during execution/testing.
- Generated: Yes
- Committed: No

---

*Structure analysis: 2026-04-11*
