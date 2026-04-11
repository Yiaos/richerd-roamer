# Testing Patterns

**Analysis Date:** 2026-04-11

## Test Framework

**Runner:**
- `pytest` (`>=7.0` declared in `pyproject.toml`)
- Config: `pytest.ini` and `[tool.pytest.ini_options]` in `pyproject.toml`

**Assertion Library:**
- Built-in `pytest` assertion rewriting with plain `assert`
- `unittest.mock` for test doubles

**Run Commands:**
```bash
.venv/bin/pytest -q
.venv/bin/pytest -q -m 'not hardware'
.venv/bin/pytest -q -m 'not hardware' --cov=src/roamer --cov-report=term-missing
```

## Test File Organization

**Location:**
- Tests live in the separate `tests/` directory, configured by `pytest.ini` and `pyproject.toml`.
- Source files are not co-located with tests; examples include `tests/test_audio.py` for `src/roamer/drivers/audio/alsa.py` and `tests/test_watch.py` for `src/roamer/drivers/camera/fswebcam.py`.

**Naming:**
- Use `test_*.py` filenames.
- Group related tests inside `Test*` classes for driver/capability modules, such as `TestAlsaDriver` in `tests/test_audio.py` and `TestEdgeDriver` in `tests/test_tts.py`.
- Leave very small utility modules as top-level test functions, such as `tests/test_output.py` and `tests/test_config.py`.

**Structure:**
```text
tests/
├── conftest.py
├── test_asr.py
├── test_audio.py
├── test_bluetooth.py
├── test_cli_audio_flow.py
├── test_config.py
├── test_output.py
├── test_sense.py
├── test_tts.py
├── test_vad.py
└── test_watch.py
```

## Test Structure

**Suite Organization:**
```python
class TestAlsaDriver:
    def test_record_success(self):
        driver = AlsaDriver({"capture_device": "hw:2,0", "sample_rate": 16000, "channels": 2})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = driver.record("/tmp/test.wav", 5.0)

        assert result["ok"] is True
```

**Patterns:**
- Follow a direct arrange/act/assert flow inside each test, as in `tests/test_audio.py`, `tests/test_watch.py`, and `tests/test_tts.py`.
- Create the subject under test explicitly inside each test instead of hiding setup in many fixtures. The suite uses only one shared fixture, `sample_config` in `tests/conftest.py`.
- Prefer nested context managers for scoped patching over decorators, matching `tests/test_sense.py`, `tests/test_watch.py`, and `tests/test_cli_audio_flow.py`.
- Validate contract details, not just truthiness. Assertions usually check specific keys like `result["error"]`, `result["duration_sec"]`, or parsed JSON fields in `tests/test_output.py` and `tests/test_cli_audio_flow.py`.

## Mocking

**Framework:** `unittest.mock`

**Patterns:**
```python
with patch("subprocess.run") as mock_run:
    mock_run.return_value = MagicMock(returncode=1, stderr=b"Model error")
    result = driver.synthesize("测试", "/tmp/test.wav")

assert result["ok"] is False
assert result["error"] == "tts_failed"
```

**What to Mock:**
- Mock subprocess boundaries (`subprocess.run`) in `tests/test_audio.py`, `tests/test_watch.py`, `tests/test_bluetooth.py`, and `tests/test_tts.py`.
- Mock filesystem checks and metadata (`pathlib.Path.exists`, `pathlib.Path.stat`, `mock_open`) in `tests/test_watch.py`, `tests/test_config.py`, and `tests/test_sense.py`.
- Mock helper methods with `patch.object(...)` when testing a coordinator method, as in `tests/test_sense.py` and `tests/test_tts.py`.
- Mock optional heavy dependencies with `patch.dict(sys.modules, ...)` before import, as in `tests/test_vad.py` for `onnxruntime` and `tests/test_asr.py` for `funasr`.
- Mock Click-facing capability classes in CLI tests rather than invoking real drivers, as in `tests/test_cli_audio_flow.py`.

**What NOT to Mock:**
- Do not mock pure dictionary/output helpers. `tests/test_output.py` and `tests/test_config.py` exercise `src/roamer/output.py` and merge logic in `src/roamer/config.py` directly.
- Do not mock the entire CLI parsing layer in command composition tests. `tests/test_cli_audio_flow.py` uses `click.testing.CliRunner` against the real `roamer.cli.main` entrypoint.

## Fixtures and Factories

**Test Data:**
```python
@pytest.fixture
def sample_config():
    return {
        "drivers": {"camera": "fswebcam", "audio": "alsa", "tts": "piper"},
        "fswebcam": {"device": "/dev/video0", "width": 1280, "height": 720},
    }
```

**Location:**
- Shared fixtures live in `tests/conftest.py`.
- Most test data is still created inline per test using dictionaries, `MagicMock()`, and `tempfile.NamedTemporaryFile(...)`, as seen in `tests/test_config.py`, `tests/test_audio.py`, and `tests/test_asr.py`.

## Coverage

**Requirements:** No minimum coverage threshold is configured in `pytest.ini` or `pyproject.toml`.

**View Coverage:**
```bash
.venv/bin/pytest -q -m 'not hardware' --cov=src/roamer --cov-report=term-missing
```

- `pytest-cov` is installed through the `dev` extra in `pyproject.toml`.
- `.coverage` and `htmlcov/` are ignored in `.gitignore`.
- Observed result on 2026-04-11: `.venv/bin/pytest -q -m 'not hardware' --cov=src/roamer --cov-report=term-missing` completed successfully with `67 passed, 8 deselected` and `TOTAL 64%` coverage.
- Lowest non-hardware coverage sits in coordinator-style capability modules: `src/roamer/capabilities/listen.py`, `src/roamer/capabilities/speak.py`, `src/roamer/capabilities/watch.py`, and `src/roamer/capabilities/_audio.py`.

## Test Types

**Unit Tests:**
- The suite is primarily unit-level. Tests isolate one driver or helper at a time and replace subprocesses, files, and external SDKs with mocks.
- Representative files: `tests/test_audio.py`, `tests/test_bluetooth.py`, `tests/test_output.py`, `tests/test_config.py`.

**Integration Tests:**
- CLI integration is covered at the command boundary with `CliRunner`, JSON parsing, and capability mocks in `tests/test_cli_audio_flow.py`.
- These tests verify argument parsing, stdout behavior, and command composition without touching real hardware.

**E2E Tests:**
- No browser or end-to-end framework is used.
- Hardware-marked tests are the closest equivalent. They run real binaries or hardware against cameras, audio devices, Bluetooth, TTS, ASR, and VAD in `tests/test_watch.py`, `tests/test_audio.py`, `tests/test_bluetooth.py`, `tests/test_tts.py`, `tests/test_asr.py`, and `tests/test_vad.py`.

## Common Patterns

**Async Testing:**
```python
# Not used in this repository.
```

**Error Testing:**
```python
with patch("subprocess.run") as mock_run:
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="arecord", timeout=10)
    result = driver.record("/tmp/test.wav", 5.0)

assert result["ok"] is False
assert result["error"] == "audio_record_failed"
assert "timed out" in result["message"]
```

- Prefer explicit failure-mode coverage for non-zero return codes, missing binaries, missing files, and timeouts, as seen throughout `tests/test_audio.py`, `tests/test_watch.py`, `tests/test_tts.py`, and `tests/test_bluetooth.py`.
- Use `capsys` when stdout/stderr separation matters, as in `tests/test_asr.py::test_transcribe_redirects_noisy_stdout_to_stderr`.
- Use the `hardware` marker for tests that touch real devices or installed models. The marker is declared in both `pytest.ini` and `tests/conftest.py`.
- No parametrized tests are present. Add new tests in the existing explicit style unless the case matrix becomes repetitive enough to justify `@pytest.mark.parametrize`.

---

*Testing analysis: 2026-04-11*
