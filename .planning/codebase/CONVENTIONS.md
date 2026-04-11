# Coding Conventions

**Analysis Date:** 2026-04-11

## Naming Patterns

**Files:**
- Use lowercase `snake_case` module names under `src/roamer/`, such as `src/roamer/config.py`, `src/roamer/capabilities/listen.py`, and `src/roamer/drivers/speech/tts/edge.py`.
- Name test modules `test_*.py` under `tests/`, such as `tests/test_cli_audio_flow.py` and `tests/test_output.py`.
- Keep package `__init__.py` files minimal and declarative, as in `src/roamer/drivers/audio/__init__.py` and `src/roamer/drivers/camera/__init__.py`.

**Functions:**
- Use `snake_case` for functions, methods, and Click command handlers: `load_config` in `src/roamer/config.py`, `audio_record` in `src/roamer/cli.py`, and `_get_network_info` in `src/roamer/capabilities/sense.py`.
- Prefix internal helpers and cached state accessors with `_`, such as `_create_temp_audio` in `src/roamer/capabilities/speak.py` and `_frames_to_segments` in `src/roamer/drivers/speech/vad/silero.py`.

**Variables:**
- Use descriptive `snake_case` local names: `driver_name`, `save_audio`, `cleanup_output`, `speech_frames`, `mock_run`.
- Use boolean names that read naturally in conditions: `is_wav` in `src/roamer/drivers/speech/tts/edge.py`, `speech_detected` in `src/roamer/drivers/speech/vad/silero.py`.
- Use uppercase constants for shared configuration and registries: `DEFAULT_CONFIG` in `src/roamer/config.py`, `VALID_STYLES` in `src/roamer/drivers/speech/tts/edge.py`, `_DRIVERS` in `src/roamer/drivers/registry.py`.

**Types:**
- Use `PascalCase` for classes and exceptions: `SenseCapability` in `src/roamer/capabilities/sense.py`, `PiperDriver` in `src/roamer/drivers/speech/tts/piper.py`, `DriverNotFoundError` in `src/roamer/errors.py`.
- Prefer built-in generics and PEP 604 unions over `typing.Dict`/`Optional`: `dict[str, Any]`, `Path | None`, `list[dict[str, Any]]` appear across `src/roamer/cli.py`, `src/roamer/config.py`, and `src/roamer/drivers/bluetooth/bluez.py`.

## Code Style

**Formatting:**
- No dedicated formatter config is detected beyond `pyproject.toml`; write code in the existing hand-formatted Python style used in `src/roamer/cli.py` and `src/roamer/capabilities/listen.py`.
- Use 4-space indentation, double-quoted strings, and a module docstring at the top of each file, matching `src/roamer/output.py`, `src/roamer/errors.py`, and every file under `tests/`.
- Keep lines within the Ruff limit `line-length = 100` configured in `pyproject.toml`.
- Break long calls across multiple lines with trailing commas, as in `src/roamer/cli.py` and `src/roamer/drivers/speech/tts/edge.py`.

**Linting:**
- Follow Ruff settings in `pyproject.toml`: `select = ["E", "F", "I", "W"]`.
- Keep imports sorted into Ruff-compatible groups and remove unused imports unless they are intentional registration side effects.
- When a module import exists only to register drivers, keep the import and annotate it with `# noqa: F401`, as done in `src/roamer/capabilities/listen.py`, `src/roamer/capabilities/speak.py`, and `src/roamer/drivers/speech/__init__.py`.

## Import Organization

**Order:**
1. Standard library imports first, such as `json`, `tempfile`, `subprocess`, `Path`.
2. Third-party imports next, such as `click`, `yaml`, `numpy`, `pytest`.
3. Local package imports last, such as `from roamer.config import load_config`.

**Path Aliases:**
- No path aliases are used.
- Import project code through the package root `roamer...`, relying on the `src/` layout declared in `pyproject.toml`.

## Error Handling

**Patterns:**
- Return structured result dictionaries instead of raising domain exceptions for operational failures. Drivers and capabilities consistently use `success()` and `error()` from `src/roamer/output.py`.
- Reserve exceptions for CLI usage mistakes and abstract interfaces. `src/roamer/cli.py` raises `click.UsageError`, while base driver classes in `src/roamer/drivers/audio/base.py` and `src/roamer/drivers/bluetooth/base.py` use `@abstractmethod`.
- Catch broad exceptions at hardware and subprocess boundaries and degrade to structured errors or empty values, as in `src/roamer/capabilities/sense.py`, `src/roamer/drivers/audio/alsa.py`, and `src/roamer/drivers/speech/asr/funasr.py`.
- Keep stdout clean for contract output. Debug and noisy library output are redirected to stderr in `src/roamer/capabilities/listen.py`, `src/roamer/drivers/speech/vad/silero.py`, and `src/roamer/drivers/speech/asr/funasr.py`.

## Logging

**Framework:** `print` to stderr and `click.echo`

**Patterns:**
- Use `click.echo()` for CLI-facing stdout/stderr output in `src/roamer/cli.py`.
- Use lightweight debug helpers that write to stderr instead of the `logging` module, as in `src/roamer/capabilities/listen.py` and `src/roamer/drivers/speech/vad/silero.py`.
- Do not print arbitrary diagnostics to stdout from libraries or drivers. Keep stdout reserved for JSON or `--text-only` payloads from `src/roamer/cli.py`.

## Comments

**When to Comment:**
- Prefer short rationale comments only where side effects or non-obvious behavior matter.
- Use registration comments for side-effect imports, such as `# Import drivers to register them` in `src/roamer/capabilities/_audio.py` and `src/roamer/capabilities/watch.py`.
- Use targeted inline comments to explain protocol requirements or shell tool behavior, such as chunk/context notes in `src/roamer/drivers/speech/vad/silero.py` and MP3-to-WAV conversion comments in `src/roamer/drivers/speech/tts/edge.py`.
- Avoid explanatory comments for straightforward assignments. Most modules rely on names and docstrings instead.

**JSDoc/TSDoc:**
- Not applicable.
- Use Python docstrings consistently at module, class, and method level with `Args:` and `Returns:` sections, as in `src/roamer/config.py`, `src/roamer/drivers/registry.py`, and `src/roamer/capabilities/sense.py`.

## Function Design

**Size:** Keep public methods focused on one capability or one shell interaction. Larger methods are still linear flows with helper extraction, as in `ListenCapability.listen()` in `src/roamer/capabilities/listen.py`.

**Parameters:** Type parameters explicitly and give concrete defaults in signatures, such as `timeout: float = 10.0`, `style: str | None = None`, and `full: bool = False` in `src/roamer/cli.py` and `src/roamer/capabilities/sense.py`.

**Return Values:** Return `dict[str, Any]` payloads with a stable `ok` flag plus capability-specific keys. Error payloads should include `error` and `message`, following `src/roamer/output.py`.

## Module Design

**Exports:**
- Keep small package exports in `__init__.py` files. Use `__all__` only for concrete public driver exports, as in `src/roamer/drivers/audio/__init__.py` and `src/roamer/drivers/camera/__init__.py`.
- Register drivers at import time with `register_driver(...)` at the bottom of each concrete driver module, as in `src/roamer/drivers/audio/alsa.py`, `src/roamer/drivers/bluetooth/bluez.py`, and `src/roamer/drivers/speech/vad/silero.py`.

**Barrel Files:**
- Lightweight barrel files are used selectively.
- `src/roamer/drivers/speech/__init__.py` exists to import subpackages for side effects.
- No broad cross-package barrel layer is used; most modules import concrete implementations directly from `roamer...`.

---

*Convention analysis: 2026-04-11*
