# SU-03T Wakeword Design

Date: 2026-05-05
Status: Draft for review

## Goal

Roamer should support hands-free conversation without manually running `roamer converse`.
The MVP wake path uses the SU-03T module as a low-power hardware trigger, then uses Roamer's
existing software audio stack to confirm speech and understand the command.

Target user flow:

```text
User says: "Richard 现在几点了"
SU-03T triggers Pi over GPIO
Roamer records with pre-roll, confirms speech with Silero, transcribes with ASR
Roamer strips the wake phrase and handles "现在几点了"
Roamer speaks the answer
```

Supported wake phrase variants:

- `Richard`
- `Rich-erd`
- `瑞彻德`

The wake phrase confirmation happens after ASR, not inside SU-03T and not through a custom
openWakeWord model.

## Hardware

Default wiring:

```text
SU-03T VCC  -> Raspberry Pi 5V, physical pin 2 or 4
SU-03T GND  -> Raspberry Pi GND, physical pin 6
SU-03T OUT  -> Raspberry Pi GPIO17 / BCM17, physical pin 11
```

Assumptions:

- SU-03T is powered from 5V through the `VCC` pin.
- SU-03T `3V3` is the module's regulated 3.3V output and should not be used as the
  normal Raspberry Pi supply input for this module.
- SU-03T OUT is a 3.3V-safe digital output.
- GPIO17 is reserved for SU-03T wake trigger.
- The first implementation assumes a rising-edge trigger. If hardware testing shows
  falling-edge behavior, this should be configurable without code changes.

Do not connect a 5V output directly to Raspberry Pi GPIO. SU-03T GPIO/UART signals are
expected to be 3.3V logic, but the OUT pin should still be checked with a meter before
connecting it to GPIO17.

## Architecture

The production wake chain is:

```text
SU-03T GPIO trigger
  -> Roamer wake service captures audio with pre-roll
  -> Silero endpointing confirms human speech and trims the utterance
  -> FunASR transcribes the utterance
  -> wake phrase matcher confirms Richard / Rich-erd / 瑞彻德
  -> remaining text is routed through existing ConverseCapability
  -> local intent or Discord fallback produces the response
  -> Roamer speaks and then enters a short follow-up window
```

Component responsibilities:

- SU-03T: L0 hardware trigger only. It wakes the Pi-side software path when it detects
  an audio event.
- GPIO wake driver: waits for SU-03T trigger events and debounces them.
- Audio pre-roll buffer: keeps the last 0.5-1.0 seconds of microphone audio so
  the wake phrase is not clipped.
- Silero VAD/endpointing: decides whether captured audio contains speech and where the
  utterance ends.
- ASR: converts speech to text.
- Wake phrase matcher: confirms the ASR text is calling Roamer, then strips the wake phrase.
- Converse state machine: handles the command text using the existing intent and fallback flow.
- systemd service: starts the wake loop at boot and restarts it after failures.

## Runtime State Machine

```text
IDLE
  -> TRIGGERED
  -> RECORDING
  -> TRANSCRIBING
  -> ROUTING
  -> SPEAKING
  -> FOLLOWUP
  -> IDLE
```

State behavior:

- `IDLE`: wait for SU-03T GPIO trigger.
- `TRIGGERED`: debounce the trigger and ignore it if Roamer is currently speaking.
- `RECORDING`: record pre-roll plus live audio through Silero endpointing.
- `TRANSCRIBING`: run ASR on the captured utterance.
- `ROUTING`: confirm wake phrase, strip it, then pass command text into existing converse logic.
- `SPEAKING`: play TTS and temporarily ignore SU-03T triggers.
- `FOLLOWUP`: allow follow-up commands for 8-12 seconds without requiring the wake phrase.

Follow-up mode prevents every sentence from needing `Richard`, while still returning to
`IDLE` after a short silence window.

## Configuration

Proposed config:

```yaml
converse:
  wakeword:
    enabled: true
    driver: su03t_gpio
    gpio_chip: gpiochip0
    gpio_line: 17
    edge: rising
    pull: down
    debounce_ms: 300
    min_interval_sec: 1.5
    pre_roll_sec: 1.0
    ignore_while_speaking: true
    prompt_sound: false
    phrases:
      - richard
      - rich erd
      - 瑞彻德
    followup_timeout_sec: 10.0

  endpoint:
    mode: vad_endpoint
    silence_sec: 1.0
    min_speech_sec: 0.2
    max_record_sec: 8.0
    pre_speech_padding_sec: 0.3
```

`prompt_sound` should default to `false` for one-shot wake commands. If Roamer speaks
`在` before listening, it forces a two-step interaction and can cause self-capture.

## Implementation Plan

### Concrete Implementation

Implement this as a new always-on wake service, not as a long-running shell loop
around `roamer converse`. The service owns the microphone while idle, waits for SU-03T
GPIO, captures one utterance, then routes the recognized command through the existing
converse intent/fallback logic.

New or changed files:

```text
src/roamer/cli/main.py
src/roamer/platform/config.py
src/roamer/plugins/interaction/actions/wake.py
src/roamer/plugins/interaction/capabilities/converse.py
src/roamer/plugins/interaction/capabilities/wake.py
src/roamer/plugins/interaction/drivers/wakeword/su03t_gpio.py
src/roamer/plugins/interaction/services/preroll_audio.py
src/roamer/plugins/interaction/services/wake_phrases.py
src/roamer/plugins/interaction/plugin.py
systemd/roamer-wake.service
install.sh
config.yaml
config.example.yaml
pyproject.toml
tests/cli/test_wake_cli.py
tests/plugins/interaction/test_su03t_gpio_driver.py
tests/plugins/interaction/test_preroll_audio.py
tests/plugins/interaction/test_wake_capability.py
tests/plugins/interaction/test_wake_phrases.py
```

CLI and action shape:

```bash
roamer wake
roamer wake --once
roamer wake --timeout 30
roamer wake --no-sound
```

`roamer wake` runs the systemd-friendly infinite loop. `--once` waits for one valid
wake command and exits, which is the main hardware test entry point.

`WakeAction.run()` should delegate to `WakeCapability.run()`:

```python
class WakeAction:
    def run(self, *, once=False, timeout=None, no_sound=False) -> dict[str, Any]:
        return WakeCapability(self.config).run(
            once=once,
            timeout=timeout,
            no_sound=no_sound,
        )
```

`plugin.py` should register `wake` as an interaction action so the CLI and future daemon
paths use the same registry pattern as `converse`, `listen`, and `speak`.

### GPIO Driver

`su03t_gpio.py` implements the existing `WakewordDriver` interface:

```python
class Su03tGpioDriver(WakewordDriver):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def wait_hit(self, timeout: float) -> bool: ...
```

Use the Python `gpiod` bindings on Raspberry Pi OS. Add a small import boundary so tests
can inject a fake chip/line and local development on macOS does not import Raspberry Pi
GPIO code during normal test collection.

Expected behavior:

- `start()` opens `gpiochip0`, configures BCM17 as input, and subscribes to `rising`
  events.
- `wait_hit(timeout)` blocks until an edge event or timeout.
- Debounce happens in software using `debounce_ms`.
- Repeated events inside `min_interval_sec` are ignored.
- `stop()` releases the GPIO line cleanly.

If `gpiod` is missing or the line cannot be opened, return a canonical
`converse.wakeword.unavailable` error through the existing converse/wake error path.

Dependency changes:

```toml
[project.optional-dependencies]
gpio = ["gpiod>=2.0"]
```

`install.sh` should install/verify the GPIO dependency on Roamer. If GPIO wake is enabled
and `gpiod` is unavailable, installation should fail with a clear message instead of
installing a broken wake service.

### Audio Pre-Roll

Add `services/preroll_audio.py` with a long-lived microphone reader:

```python
class PreRollAudioSource:
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def snapshot(self) -> list[bytes]: ...
    def capture_iter(self, max_duration_sec: float) -> Iterator[bytes]: ...
    def chunks_after_snapshot(self, snapshot: list[bytes], max_duration_sec: float) -> Iterator[bytes]: ...
```

Implementation detail:

- Reuse `AudioCapability.stream_chunks()` so the actual capture device, sample rate, and
  channel count still come from `alsa`.
- Run the ALSA chunk reader in a background thread.
- Store the last `pre_roll_sec` of chunks in a bounded `deque`.
- On GPIO trigger, `capture_iter()` snapshots the deque and passes `snapshot + live chunks`
  into the existing `EndpointRecorder`.
- Keep the chunk duration aligned with `EndpointConfig.chunk_duration_sec` so Silero's
  512-sample minimum still holds.

This avoids changing the core ASR driver and keeps one-shot input like
`Richard 现在几点了` from losing the first word.

### Endpointing and ASR Reuse

Do not create a second ASR path. The wake service should reuse the existing listen stack:

```text
PreRollAudioSource chunks
  -> EndpointRecorder
  -> Silero VAD probability through ChunkVadAdapter
  -> temporary WAV
  -> existing ASR driver transcribe()
```

The only required change is to allow endpointing to receive a custom chunk iterator
instead of always constructing it from `AudioCapability.stream_chunks()` inside
`ListenCapability.listen()`. Prefer adding a small helper service rather than duplicating
the load-wav, VAD, trim, and ASR code.

### Wake Phrase Matching

Add `services/wake_phrases.py`:

```python
@dataclass(frozen=True)
class WakeMatch:
    matched: bool
    phrase: str | None
    command_text: str

def match_wake_phrase(text: str, phrases: Sequence[str]) -> WakeMatch: ...
```

Normalization rules:

- Lowercase ASCII.
- Strip leading punctuation and spaces.
- Treat `richard`, `rich erd`, and `rich-erd` as equivalent forms.
- Keep Chinese text intact.
- Match only at the beginning of the utterance outside follow-up mode.

Examples:

```text
"Richard 现在几点了" -> matched, command_text="现在几点了"
"rich-erd 回家" -> matched, command_text="回家"
"瑞彻德 看一下" -> matched, command_text="看一下"
"现在几点了" outside FOLLOWUP -> not matched
"现在几点了" inside FOLLOWUP -> route directly
```

If ASR returns only the wake phrase, enter `FOLLOWUP` and wait for the next utterance
without sending an empty command to Discord fallback.

### Converse Routing Refactor

`ConverseCapability.run()` currently couples listening, intent matching, local actions,
Discord fallback, and speaking in one method. Wake mode needs to route already-transcribed
text. Refactor without changing current CLI behavior:

```python
class ConverseCapability:
    def route_text(
        self,
        text: str,
        *,
        session_id: str,
        turn_id: int,
        no_sound: bool,
    ) -> dict[str, Any]:
        ...
```

`run()` should call `route_text()` after its own listen stage. `WakeCapability` should
call the same method after ASR and wake phrase stripping. This keeps local intents,
Discord fallback, and TTS behavior consistent between manual `roamer converse` and
hands-free wake mode.

### Wake Loop State Machine

`WakeCapability` owns the runtime state:

```python
while running:
    state = "IDLE"
    hit = wake_driver.wait_hit(timeout=poll_timeout)
    if not hit:
        continue

    if speaking_gate.active:
        record_metric("ignored_while_speaking")
        continue

    state = "RECORDING"
    audio_result = endpoint_recorder.record(pre_roll_source.capture_iter())
    if no_speech:
        continue

    state = "TRANSCRIBING"
    text = asr.transcribe(audio_result.audio_path)

    state = "ROUTING"
    match = match_wake_phrase(text, phrases)
    if not match.matched and not in_followup_window:
        continue

    command_text = match.command_text if match.matched else text
    if not command_text:
        enter_followup_window()
        continue

    state = "SPEAKING"
    converse.route_text(command_text, ...)
    enter_followup_window()
```

Use a local `threading.Event` or small `SpeakingGate` context manager around TTS playback
so GPIO events during Roamer's own speech are ignored. MVP does not implement full AEC.

### systemd

Add `systemd/roamer-wake.service`:

```ini
[Unit]
Description=Roamer SU-03T wake loop
After=network-online.target roamer-serve.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/richerd/worksp/richerd-roamer
ExecStart=/home/richerd/.venv/roamer/bin/roamer wake
Restart=on-failure
RestartSec=2
RuntimeDirectory=roamer
RuntimeDirectoryMode=0700
UMask=0077

[Install]
WantedBy=multi-user.target
```

`install.sh` should install this service when `converse.wakeword.enabled: true` and
`converse.wakeword.driver: su03t_gpio`. It should restart `roamer-wake.service` after
code/config changes and verify the service reaches an active state.

Manual test commands:

```bash
sudo systemctl status roamer-wake.service
journalctl -u roamer-wake.service -f
roamer wake --once --timeout 30
```

P1 implementation:

1. Add an SU-03T GPIO wake driver using a Raspberry Pi GPIO library available on Roamer.
2. Add a wake-loop capability or service that owns the runtime state machine.
3. Add an audio ring buffer or recorder path that can prepend `pre_roll_sec` audio to
   the utterance after a GPIO trigger.
4. Reuse existing `EndpointRecorder`, `SileroDriver`, and FunASR listen flow where possible.
5. Add a wake phrase matcher that normalizes ASR text and supports `Richard`, `Rich-erd`,
   and `瑞彻德`.
6. Route stripped command text through existing converse intent/fallback logic.
7. Add a systemd service for the hands-free wake loop.
8. Extend `install.sh` to validate required GPIO/audio dependencies and install the service.
9. Add tests for GPIO trigger debouncing, wake phrase matching, follow-up mode, and
   speaking-state trigger suppression.

P2 implementation:

- UART mode for richer SU-03T command events.
- Metrics for trigger count, confirmed speech count, wake match rate, false trigger rate,
  and trigger-to-response latency.
- Tuning command for threshold and timeout calibration.
- Real AEC or barge-in support. MVP only ignores triggers while speaking.

## Error Handling

- If GPIO setup fails, service exits with a clear configuration error.
- If SU-03T triggers but Silero detects no speech, Roamer records a filtered trigger and
  returns to `IDLE`.
- If ASR returns text without a wake phrase while outside `FOLLOWUP`, Roamer ignores it.
- If ASR returns only the wake phrase, Roamer can optionally speak a short prompt or wait
  briefly for follow-up; MVP should return to `FOLLOWUP`.
- If TTS is playing, GPIO triggers are ignored until playback ends plus a short cooldown.

## Testing

Automated tests:

- SU-03T GPIO driver handles rising edge, debounce, timeout, and cleanup.
- Wake phrase matcher accepts English and Chinese variants.
- Wake phrase matcher strips only the prefix and preserves command text.
- Wake loop ignores triggers while speaking.
- Follow-up mode routes text without a wake phrase until timeout.

Roamer hardware tests:

1. Boot Roamer and verify wake service is active.
2. Say `Richard 现在几点了` ten times at normal distance.
3. Say `Rich-erd 现在几点了` ten times.
4. Say `瑞彻德 现在几点了` ten times.
5. Leave Roamer idle for ten minutes and count false triggers.
6. Verify Roamer does not trigger on its own TTS playback.
7. Verify follow-up command works without repeating `Richard`.

MVP acceptance criteria:

- At least 8/10 successful wake-and-command runs for each supported wake phrase in a quiet room.
- No repeated self-trigger loop during TTS playback.
- False triggers are filtered by Silero/ASR and do not reach Discord fallback as user commands.
- Wake service starts on boot and restarts after a crash.
