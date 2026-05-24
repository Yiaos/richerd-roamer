# Phase B1 Progress Checklist

Source plan: `docs/plans/2026-05-19-phase-b1-hearing-speech.md`

Rule for this phase:
- Do not read Phase B2 until every non-hardware Phase B1 task below is `VERIFIED` or explicitly `HARDWARE-EXCLUDED`.
- Mock/fake drivers may replace device I/O in tests, but the production driver boundary and non-hardware behavior must remain implemented.
- A task is not complete until focused tests and the phase verification commands pass.

Status key:
- `TODO`: not audited or not implemented.
- `IMPLEMENTED`: code exists but full B1 verification is not complete.
- `VERIFIED`: implementation and verification evidence satisfy the B1 plan/spec.
- `HARDWARE-EXCLUDED`: physical device execution only; interface, subprocess behavior, parsing, timeout, and fake-driver tests still required.
- `BLOCKED`: cannot be verified without user input or external dependency.

## Current Gate

- Current phase: Phase B1 only.
- Next phase allowed: yes, Phase B2 may be read after this file update.
- Entry evidence: Phase A verified in `docs/progress/phase-a-checklist.md`.
- Latest B1 verification: 2026-05-23, passed.

## Task 1: Hearing Module Skeleton + Driver Protocols

Status: VERIFIED

Required evidence:
- HearingModule implements CapabilityModule Protocol.
- AudioCaptureDriver, VadDriver, WakewordDriver, RealtimeSttDriver, BatchAsrDriver protocols.
- start/stop/health_check lifecycle.
- Produced/consumed event declarations.
- `pytest tests/roamerd/capabilities/hearing/test_module.py -v`.
- `mypy --strict src/roamerd/capabilities/hearing/`.

## Task 2: ALSA Capture + Silero VAD + Endpointing

Status: VERIFIED

Required evidence:
- ALSA capture subprocess interface with fake subprocess tests.
- Silero VAD adapter/interface with deterministic fake model tests.
- Endpointing state machine for silence/min/max/pre-padding and WAV save.
- Hardware microphone execution is `HARDWARE-EXCLUDED`; code and fake-subprocess tests are not excluded.
- `pytest tests/roamerd/capabilities/hearing/test_alsa.py tests/roamerd/capabilities/hearing/test_vad.py tests/roamerd/capabilities/hearing/test_endpointing.py -v`.

## Task 3: Network ASR + FunASR Batch Fallback

Status: VERIFIED

Required evidence:
- Network ASR WebSocket protocol, timeout, close semantics, text normalization.
- FunASR batch driver boundary and fake model tests.
- HearingModule fallback from realtime to batch on connect failure/timeout.
- External ASR service execution is `HARDWARE-EXCLUDED`/external-excluded; protocol and fake server tests are not excluded.
- `pytest tests/roamerd/capabilities/hearing/test_network_asr.py tests/roamerd/capabilities/hearing/test_funasr.py -v`.

## Task 4: SU-03T GPIO Wakeword + OpenWakeword Compat

Status: VERIFIED

Required evidence:
- SU-03T GPIO driver boundary with debounce/min interval and fake gpiod tests.
- OpenWakeword compatibility driver boundary with fake detector tests.
- Wake loop state machine: idle, wake_detected, listening, follow-up window.
- Ignore-while-speaking behavior.
- Follow-up generation safety.
- Wake phrase stripping golden tests.
- Pre-roll playback timing and failure tolerance.
- Physical GPIO/openwakeword model execution is `HARDWARE-EXCLUDED`; fake-driver behavior tests are not excluded.
- `pytest tests/roamerd/capabilities/hearing/test_wake.py -v` or equivalent split tests.

## Task 5: Speech Module Skeleton + TTS Drivers

Status: VERIFIED

Required evidence:
- SpeechModule implements CapabilityModule Protocol.
- TtsDriver Protocol and SynthResult.
- Edge TTS subprocess driver with fake subprocess tests.
- Piper subprocess driver with fake subprocess tests.
- Fallback behavior from Edge to Piper.
- `pytest tests/roamerd/capabilities/speech/test_module.py tests/roamerd/capabilities/speech/test_tts.py -v`.
- `mypy --strict src/roamerd/capabilities/speech/`.

## Task 6: ALSA Playback + Bluetooth Reconnect

Status: VERIFIED

Required evidence:
- BluetoothDriver Protocol.
- BlueZ/bluetoothctl/pactl parser and timeout behavior with fake subprocess tests.
- ALSA playback subprocess behavior with fake subprocess tests.
- Playback partial-success semantics.
- Playback generation/stale behavior.
- StateManager-visible playback state remains in sync.
- Physical speaker/Bluetooth execution is `HARDWARE-EXCLUDED`; parser/subprocess fake tests are not excluded.
- `pytest tests/roamerd/capabilities/speech/test_playback.py tests/roamerd/capabilities/speech/test_bluetooth.py -v`.

## Task 7: Hearing + Speech Integration

Status: VERIFIED

Required evidence:
- Mock wake -> `hearing.wake_triggered`.
- Mock record/VAD/STT -> `hearing.transcript_ready` with metadata.
- Speak action -> TTS -> playback -> `speech.playback_completed`.
- Playback active wake is ignored without recording.
- Realtime STT unavailable -> batch fallback.
- `pytest tests/roamerd/capabilities/test_hearing_speech_integration.py -v`.

## Phase Verification

Status: VERIFIED

Required evidence:
- `pytest tests/roamerd/capabilities/hearing/ tests/roamerd/capabilities/speech/ -v`.
- `pytest tests/roamerd/capabilities/test_hearing_speech_integration.py -v`.
- `pytest tests/roamerd/contracts_migration -q`.
- `mypy --strict src/roamerd/capabilities/hearing/ src/roamerd/capabilities/speech/`.
- `ruff check src/roamerd/capabilities/ tests/roamerd/capabilities/`.
- Wake -> listen -> STT -> speak end-to-end mock chain passes.

## Verification Log

- `pytest tests/roamerd/capabilities/hearing/ tests/roamerd/capabilities/speech/ tests/roamerd/capabilities/test_hearing_speech_integration.py tests/roamerd/contracts_migration -q` -> 36 passed.
- `mypy --strict src/roamerd/capabilities/hearing/ src/roamerd/capabilities/speech/` -> success, 33 source files.
- `ruff check src/roamerd/capabilities/hearing/ src/roamerd/capabilities/speech/ tests/roamerd/capabilities/hearing/ tests/roamerd/capabilities/speech/ tests/roamerd/capabilities/test_hearing_speech_integration.py` -> all checks passed.
- `pytest tests/roamerd/ -q --tb=short` -> 169 passed.
- `mypy src/roamerd/ --strict` -> success, 101 source files.
- `ruff check src/roamerd/ tests/roamerd/` -> all checks passed.
- Added missing B1 behavior-contract coverage:
  - ALSA capture subprocess boundary with fake runner.
  - Silero VAD threshold adapter.
  - Endpointing min/silence/max/pre-roll and WAV save.
  - Network ASR WebSocket-style protocol and normalization.
  - FunASR batch driver boundary.
  - SU-03T GPIO min-interval debounce and OpenWakeword adapter.
  - Edge TTS, Piper, and TTS fallback.
  - ALSA playback, BlueZ command parsing, Bluetooth reconnect wrapper.
  - Playback generation/staleness and StateManager playback generation.
  - Hearing listen action cancellation with no stale transcript/fallback.
  - WakeGate in `capabilities/hearing/wake_loop.py` using StateManager playback state.
