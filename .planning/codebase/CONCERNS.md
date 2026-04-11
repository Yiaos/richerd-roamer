# Codebase Concerns

**Analysis Date:** 2026-04-11

## Tech Debt

**Hardware-gated tests run as normal suite members:**
- Issue: `@pytest.mark.hardware` tests in `tests/test_audio.py`, `tests/test_tts.py`, `tests/test_vad.py`, and `tests/test_watch.py` are collected and executed by default instead of being skipped behind an environment flag or hardware probe.
- Files: `tests/test_audio.py`, `tests/test_tts.py`, `tests/test_vad.py`, `tests/test_watch.py`, `pytest.ini`, `tests/conftest.py`
- Impact: `./.venv/bin/pytest -q` currently fails on machines without the expected devices, models, or networked TTS. The non-hardware suite is healthy (`./.venv/bin/pytest -q -m 'not hardware'` passes), so the default signal is noisier than the actual code health.
- Fix approach: Gate hardware tests with `skipif` or an opt-in env var such as `ROAMER_RUN_HARDWARE_TESTS=1`, and keep default CI/local runs on `not hardware`.

**Motion capability is configured and documented but not implemented:**
- Issue: motion defaults to `valetudo` in configuration and is described in the README, but there is no CLI command or driver path that exposes motion behavior.
- Files: `src/roamer/config.py`, `config.example.yaml`, `README.md`, `src/roamer/cli.py`
- Impact: callers can infer that motion is part of the supported contract even though no executable feature exists. Future work has to unwind that mismatch before building on top of it.
- Fix approach: Either implement a real motion capability end-to-end or remove the motion driver from defaults and docs until code exists.

**Health reporting is hard-coded to one Linux host shape:**
- Issue: `SenseCapability` mixes `/proc` parsing, `/sys` temperature paths, and command-line probes such as `iwgetid`, `tailscale`, `arecord`, and `bluetoothctl`, while hardware checks ignore configured device names.
- Files: `src/roamer/capabilities/sense.py`, `src/roamer/config.py`
- Impact: `roamer sense --full` can report false negatives on valid custom setups and silently degrade on non-Linux environments instead of exposing a deliberate compatibility boundary.
- Fix approach: Centralize platform detection, read configured devices from `load_config`, and return explicit `"unsupported"` or `"not_configured"` states rather than generic falsey values.

## Known Bugs

**`cpu_percent` is not current CPU usage:**
- Symptoms: `SenseCapability._get_cpu_percent()` returns a ratio of cumulative non-idle ticks since boot, not a sampled utilization percentage.
- Files: `src/roamer/capabilities/sense.py`
- Trigger: Any `roamer sense` call that reads `cpu_percent`.
- Workaround: Treat `cpu_percent` as unreliable until the code samples `/proc/stat` twice over an interval or uses a system library designed for CPU utilization.

**Fractional audio timeouts are truncated before recording:**
- Symptoms: `listen --timeout 2.9` or `audio record --duration 2.9` records for `2` seconds because `AlsaDriver.record()` passes `str(int(duration))` to `arecord`.
- Files: `src/roamer/drivers/audio/alsa.py`, `src/roamer/capabilities/listen.py`, `src/roamer/cli.py`
- Trigger: Any non-integer duration passed through `roamer listen --timeout` or `roamer audio record --duration`.
- Workaround: Use integer values only until the driver switches to a duration strategy that preserves sub-second intent.

**`speak` reports success even when playback fails:**
- Symptoms: `SpeakCapability.speak()` returns `{"ok": true, "played": false}` after synthesis if Bluetooth connection or local playback fails.
- Files: `src/roamer/capabilities/speak.py`
- Trigger: Missing Bluetooth sink, failed `bluetoothctl connect`, failed `aplay`, or other playback-layer errors while `play=True`.
- Workaround: Downstream callers must inspect `played` manually instead of trusting `ok`.

**Short trailing speech can be dropped by VAD chunking:**
- Symptoms: `SileroDriver.detect()` only iterates over full 512-sample chunks and does not pad or process the final remainder, so speech near the end of a clip can be missed.
- Files: `src/roamer/drivers/speech/vad/silero.py`, `src/roamer/capabilities/listen.py`
- Trigger: Short utterances, clips shorter than one chunk, or speech that lands in the final partial chunk after recording.
- Workaround: Increase recording padding and avoid aggressive timeout limits until the VAD handles tail chunks explicitly.

## Security Considerations

**Edge SSML content is interpolated without XML escaping:**
- Risk: User text is embedded directly into the SSML payload. Characters such as `<`, `>`, or `&` can break the XML request or alter synthesized markup semantics.
- Files: `src/roamer/drivers/speech/tts/edge.py`
- Current mitigation: `style` is limited to a fixed allowlist in `VALID_STYLES`, which constrains one injection surface but does not protect the text node itself.
- Recommendations: Escape SSML text content before interpolation and add regression tests for reserved XML characters.

## Performance Bottlenecks

**Listen path is fully batch-oriented and disk-backed:**
- Problem: `listen` records the whole clip to disk, loads the full WAV into memory, runs VAD across the full array, writes a trimmed WAV, and only then starts ASR.
- Files: `src/roamer/capabilities/listen.py`, `src/roamer/drivers/audio/alsa.py`, `src/roamer/drivers/speech/vad/silero.py`, `src/roamer/drivers/speech/asr/funasr.py`
- Cause: The pipeline is synchronous and file-based end to end.
- Improvement path: Move to streaming capture, incremental VAD, and direct ASR handoff so latency scales with speech length instead of max timeout.

## Fragile Areas

**Driver loading depends on import side effects:**
- Files: `src/roamer/drivers/registry.py`, `src/roamer/capabilities/watch.py`, `src/roamer/capabilities/_audio.py`, `src/roamer/capabilities/listen.py`, `src/roamer/capabilities/speak.py`, `src/roamer/drivers/speech/__init__.py`
- Why fragile: new code must remember to import the package that registers drivers before calling `get_driver()`. Missing one import yields a runtime `DriverNotFoundError` instead of a static wiring failure.
- Safe modification: add a single bootstrap import path for all built-in drivers or replace side-effect registration with explicit registry construction.
- Test coverage: indirect only. There is no dedicated test that proves every configured default driver is registered before use.

**Sense hardware checks can diverge from actual runtime configuration:**
- Files: `src/roamer/capabilities/sense.py`, `src/roamer/config.py`, `config.example.yaml`
- Why fragile: `_check_camera()` always tests `/dev/video0`, `_check_microphone()` only checks whether any ALSA card exists, and neither reads configured driver/device settings.
- Safe modification: route health checks through the configured driver or read the same config keys used by `watch` and `audio`.
- Test coverage: `tests/test_sense.py` covers mocked happy paths but does not verify config-aware health behavior.

## Scaling Limits

**Hardware access is single-process and uncoordinated:**
- Current capacity: one `watch`, `listen`, or `speak` invocation can realistically own the camera or audio device at a time on the target machine.
- Limit: concurrent callers can race on `/dev/video0`, ALSA devices, Bluetooth sink state, and temp files under `/tmp`.
- Scaling path: introduce device reservation/locking, structured job control, and a long-lived service layer if multiple callers or automation loops will share the same host.

## Dependencies at Risk

**Optional speech stack fails late at runtime:**
- Risk: the speech path depends on extras and local model files that are not validated at startup: `funasr`, `onnxruntime`, Piper binaries, and on-disk models.
- Impact: installs that succeed without `.[speech]` or without model assets fail only when `listen` or `speak` is invoked.
- Migration plan: add a `roamer doctor` or startup preflight that verifies Python extras, binaries, and configured model paths before capability execution.

**System binaries are a hidden deployment contract:**
- Risk: camera, audio, Bluetooth, and cloud-TTS flows shell out to `fswebcam`, `arecord`, `aplay`, `bluetoothctl`, `pactl`, `edge-tts`, `ffmpeg`, and `ffprobe`.
- Impact: host drift or minimal images break capabilities even when Python dependencies are installed correctly.
- Migration plan: document an explicit host package list, check each binary during health/preflight, or replace shell dependencies with maintained Python integrations where practical.

## Missing Critical Features

**Motion control contract has no executable implementation:**
- Problem: the repository advertises motion as a near-term MVP capability and ships motion config defaults, but there is no motion command in `src/roamer/cli.py` and no motion execution path exposed to callers.
- Blocks: end-to-end mobility flows, status/position/home/goto orchestration, and any planner that expects the documented Valetudo control surface.

## Test Coverage Gaps

**Listen orchestration is not directly unit-tested:**
- What's not tested: the record -> load WAV -> VAD -> trim -> ASR flow in `ListenCapability.listen()`, including cleanup, VAD failure handling, and ASR failure handling.
- Files: `src/roamer/capabilities/listen.py`
- Risk: the most integration-heavy voice-input path can regress even while the driver-level mocks stay green.
- Priority: High

**Speak playback failure semantics are untested:**
- What's not tested: `SpeakCapability.speak()` behavior when Bluetooth connection fails or `AudioCapability.play()` returns an error after successful synthesis.
- Files: `src/roamer/capabilities/speak.py`, `tests/test_cli_audio_flow.py`, `tests/test_tts.py`
- Risk: callers may continue to receive `"ok": true` without emitted audio and no test will catch the contract mismatch.
- Priority: High

**ASR hardware test is an empty placeholder:**
- What's not tested: real FunASR transcription against a known WAV sample.
- Files: `tests/test_asr.py`
- Risk: the suite has no executable proof that the configured ASR stack works on a real host.
- Priority: Medium

**Sense metrics are validated structurally, not semantically:**
- What's not tested: actual CPU utilization correctness, Wi-Fi parsing quality, Tailscale probing, and config-aware hardware checks.
- Files: `src/roamer/capabilities/sense.py`, `tests/test_sense.py`
- Risk: misleading system-health output can ship unnoticed because tests only assert shape and mocked values.
- Priority: Medium

---

*Concerns audit: 2026-04-11*
