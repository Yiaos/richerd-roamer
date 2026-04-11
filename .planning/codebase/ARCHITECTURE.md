# Architecture

**Analysis Date:** 2026-04-11

## Pattern Overview

**Overall:** Layered CLI architecture with configuration-driven capability orchestration and registry-based driver plugins.

**Key Characteristics:**
- CLI commands in `src/roamer/cli.py` are thin handlers that parse options and delegate work to capability objects.
- Capability classes in `src/roamer/capabilities/` resolve concrete drivers from config via `src/roamer/drivers/registry.py`.
- Driver implementations in `src/roamer/drivers/**` isolate hardware/tooling integration and return a consistent JSON dict contract from `src/roamer/output.py`.

## Layers

**CLI Layer:**
- Purpose: Parse command-line input, enforce command option validation, and emit final JSON/text output.
- Location: `src/roamer/cli.py`
- Contains: Click command groups (`main`, `audio`, `bt`) and command handlers (`watch`, `speak`, `listen`, `sense`, `audio record`, `audio play`, `bt status`, `bt connect`).
- Depends on: `src/roamer/config.py`, `src/roamer/capabilities/*.py`, `click`, `json`.
- Used by: Console script entry point `roamer = "roamer.cli:main"` in `pyproject.toml`.

**Capability Layer:**
- Purpose: Coordinate business-level operations (capture, speak, listen, status) and compose one or more drivers.
- Location: `src/roamer/capabilities/`
- Contains: Base capability `src/roamer/capabilities/base.py` plus orchestration modules `watch.py`, `speak.py`, `listen.py`, `sense.py`, `_audio.py`.
- Depends on: `src/roamer/config.py`, `src/roamer/drivers/registry.py`, selected driver packages imported for registration side effects.
- Used by: Command handlers in `src/roamer/cli.py`.

**Driver Abstraction Layer:**
- Purpose: Define stable interfaces per device domain.
- Location: `src/roamer/drivers/*/base.py` and `src/roamer/drivers/speech/*/base.py`
- Contains: Abstract classes `CameraDriver`, `AudioDriver`, `BluetoothDriver`, `TTSDriver`, `ASRDriver`, `VADDriver`.
- Depends on: Standard library `abc`, typing; numpy for VAD interface in `src/roamer/drivers/speech/vad/base.py`.
- Used by: Concrete drivers in each domain folder.

**Driver Registry Layer:**
- Purpose: Provide runtime lookup and construction of concrete drivers.
- Location: `src/roamer/drivers/registry.py`
- Contains: In-memory map `_DRIVERS`, registration API `register_driver`, factory `get_driver`, and discovery function `list_drivers`.
- Depends on: Exception type `DriverNotFoundError` from `src/roamer/errors.py`.
- Used by: Capabilities in `src/roamer/capabilities/*.py` and all driver implementation modules that self-register.

**Driver Implementation Layer:**
- Purpose: Execute external tools/models and convert results/errors into the shared output contract.
- Location: `src/roamer/drivers/camera/fswebcam.py`, `src/roamer/drivers/audio/alsa.py`, `src/roamer/drivers/bluetooth/bluez.py`, `src/roamer/drivers/speech/asr/funasr.py`, `src/roamer/drivers/speech/tts/piper.py`, `src/roamer/drivers/speech/tts/edge.py`, `src/roamer/drivers/speech/vad/silero.py`
- Contains: Concrete driver classes and `register_driver(...)` calls.
- Depends on: `subprocess`, model/runtime libraries, filesystem, and `src/roamer/output.py`.
- Used by: Capability classes via `get_driver(...)`.

**Support Layer:**
- Purpose: Shared config, output, and error primitives.
- Location: `src/roamer/config.py`, `src/roamer/output.py`, `src/roamer/errors.py`
- Contains: Default configuration + deep merge, JSON response builders, typed domain exception classes.
- Depends on: `yaml` and standard library.
- Used by: CLI, capabilities, and drivers across the codebase.

## Data Flow

**Command Execution Flow (`listen` as representative):**

1. `roamer listen ...` is dispatched by Click in `src/roamer/cli.py`, which loads config once in `main(...)` via `load_config(...)` from `src/roamer/config.py`.
2. The `listen` handler constructs `ListenCapability` (`src/roamer/capabilities/listen.py`), which resolves `vad` and `asr` drivers through `get_driver_name(...)`/`get_driver_config(...)` and `get_driver(...)`.
3. `ListenCapability.listen(...)` records audio through `AudioCapability` (`src/roamer/capabilities/_audio.py`), runs VAD (`src/roamer/drivers/speech/vad/silero.py`), then runs ASR (`src/roamer/drivers/speech/asr/funasr.py`), and returns a dict from `success(...)`/`error(...)` in `src/roamer/output.py`.
4. `src/roamer/cli.py` emits the result as JSON (default) or plain text for `--text-only`, and sets non-zero exit on text-only errors.

**State Management:**
- Runtime state is process-local and mostly ephemeral: command handlers create fresh capability objects per invocation in `src/roamer/cli.py`.
- Driver registry state is module-global (`_DRIVERS`) in `src/roamer/drivers/registry.py` and is populated by import-time side effects in driver modules.
- Long-lived model objects are cached per capability instance in driver objects (`_model` in `src/roamer/drivers/speech/asr/funasr.py`, `_session` in `src/roamer/drivers/speech/vad/silero.py`) during one command process.

## Key Abstractions

**Capability Abstraction:**
- Purpose: Encapsulate high-level user-facing actions independent of specific hardware/software backends.
- Examples: `src/roamer/capabilities/watch.py`, `src/roamer/capabilities/speak.py`, `src/roamer/capabilities/listen.py`, `src/roamer/capabilities/sense.py`
- Pattern: Subclasses of `Capability` (`src/roamer/capabilities/base.py`) with constructor-based driver binding.

**Driver Interface Abstraction:**
- Purpose: Enforce method contracts for each integration domain.
- Examples: `src/roamer/drivers/audio/base.py`, `src/roamer/drivers/camera/base.py`, `src/roamer/drivers/speech/tts/base.py`
- Pattern: Abstract base classes with concrete implementations registering themselves.

**Registry Abstraction:**
- Purpose: Decouple capability code from concrete class imports at call sites.
- Examples: `src/roamer/drivers/registry.py`, `src/roamer/drivers/__init__.py`, `src/roamer/drivers/speech/__init__.py`
- Pattern: String-keyed factory with lazy module import for registration side effects.

**Output Contract Abstraction:**
- Purpose: Keep all command responses machine-consumable and predictable.
- Examples: `src/roamer/output.py`, JSON emission in `src/roamer/cli.py`
- Pattern: Dict payloads with required `ok` boolean and structured error fields (`error`, `message`) on failure.

## Entry Points

**Console Script Entry Point:**
- Location: `pyproject.toml`
- Triggers: `roamer` command invocation after package install.
- Responsibilities: Map shell command `roamer` to Click group `roamer.cli:main`.

**CLI Root Group:**
- Location: `src/roamer/cli.py`
- Triggers: Process start via `roamer` command or `python -m`/direct script execution.
- Responsibilities: Load config, register context, dispatch command handlers.

**Direct Module Execution:**
- Location: `src/roamer/cli.py`
- Triggers: `python src/roamer/cli.py` style invocation through `if __name__ == "__main__":`.
- Responsibilities: Start the same Click command group.

## Error Handling

**Strategy:** Return structured error dictionaries from capabilities/drivers and print deterministic JSON at the CLI boundary.

**Patterns:**
- Drivers convert subprocess/model/runtime failures into `error(...)` payloads in files such as `src/roamer/drivers/audio/alsa.py` and `src/roamer/drivers/camera/fswebcam.py`.
- CLI-level usage validation raises `click.UsageError` in `src/roamer/cli.py` for invalid argument combinations and empty input.

## Cross-Cutting Concerns

**Logging:** Minimal and local; debug traces are emitted to stderr in `src/roamer/capabilities/listen.py` and `src/roamer/drivers/speech/vad/silero.py`. ASR model stdout noise is redirected to stderr in `src/roamer/drivers/speech/asr/funasr.py`.
**Validation:** Option/argument validation is done via Click types in `src/roamer/cli.py` (for example, range-bounded image dimensions). Driver existence/config fallback is handled in `src/roamer/config.py` plus runtime lookup in `src/roamer/drivers/registry.py`.
**Authentication:** Not detected in current architecture (`src/roamer/cli.py`, `src/roamer/capabilities/`, `src/roamer/drivers/` have no auth provider or token-based request flow).

---

*Architecture analysis: 2026-04-11*
