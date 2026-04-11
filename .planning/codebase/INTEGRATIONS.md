# External Integrations

**Analysis Date:** 2026-04-11

## APIs & External Services

**Speech Services:**
- Microsoft Edge TTS - Cloud text-to-speech option used by `src/roamer/drivers/speech/tts/edge.py` when the configured `tts` driver is `edge`.
  - SDK/Client: `edge-tts` command-line tool invoked through `subprocess.run()` in `src/roamer/drivers/speech/tts/edge.py`
  - Auth: None configured in repository code or config files; the integration relies on the `edge-tts` client behavior rather than explicit credentials in `src/roamer/drivers/speech/tts/edge.py`

**Local ML Inference:**
- FunASR - Speech recognition backend used by `src/roamer/drivers/speech/asr/funasr.py` and selected through the `drivers.asr` config in `src/roamer/config.py` or `config.example.yaml`.
  - SDK/Client: `funasr.AutoModel` imported dynamically in `src/roamer/drivers/speech/asr/funasr.py`
  - Auth: None; model selection is configuration-driven through the `funasr.model` key in `src/roamer/config.py`
- Silero VAD - Voice activity detection for recorded audio in `src/roamer/drivers/speech/vad/silero.py`.
  - SDK/Client: `onnxruntime.InferenceSession` plus local ONNX file path from `src/roamer/config.py` or `config.example.yaml`
  - Auth: None; access is to a local model file referenced by the `silero.model` config key
- Piper - Offline TTS path used by `src/roamer/drivers/speech/tts/piper.py`.
  - SDK/Client: Local `piper` binary invoked with `subprocess.run()` in `src/roamer/drivers/speech/tts/piper.py`
  - Auth: None; binary and model locations come from the `piper.binary` and `piper.model` config keys in `src/roamer/config.py`

**Hardware and OS Services:**
- ALSA utilities - Microphone capture and speaker playback in `src/roamer/drivers/audio/alsa.py`.
  - SDK/Client: `arecord` and `aplay` subprocess calls in `src/roamer/drivers/audio/alsa.py`
  - Auth: None
- BlueZ - Bluetooth status and device connection in `src/roamer/drivers/bluetooth/bluez.py`, plus speaker auto-connect in `src/roamer/capabilities/speak.py`.
  - SDK/Client: `bluetoothctl` subprocess calls in `src/roamer/drivers/bluetooth/bluez.py` and `src/roamer/capabilities/speak.py`
  - Auth: None; target device selection is by `bluetooth.speaker_mac` in `config.example.yaml`
- PulseAudio/PipeWire control surface - Bluetooth sink detection before playback in `src/roamer/capabilities/speak.py`.
  - SDK/Client: `pactl list sinks short` in `src/roamer/capabilities/speak.py`
  - Auth: None
- Camera capture - Visual snapshots through `src/roamer/drivers/camera/fswebcam.py`.
  - SDK/Client: `fswebcam` subprocess call in `src/roamer/drivers/camera/fswebcam.py`
  - Auth: None; camera device path is configured with `fswebcam.device` in `src/roamer/config.py`
- Host/network inspection - System self-reporting in `src/roamer/capabilities/sense.py`.
  - SDK/Client: local reads from `/proc/uptime`, `/proc/stat`, `/proc/meminfo`, `/proc/net/wireless`, `/sys/class/thermal/*`, plus `iwgetid` and `tailscale`
  - Auth: None

**Configured but Not Implemented:**
- Valetudo - Motion integration is referenced in `README.md`, `src/roamer/config.py`, and `config.example.yaml`, but no Valetudo driver or HTTP client exists under `src/roamer/drivers/`. Treat it as a configuration placeholder, not an active integration.
  - SDK/Client: Not detected in source files under `src/roamer/`
  - Auth: Not applicable

## Data Storage

**Databases:**
- None detected. No ORM, SQL driver, or database configuration is present in `pyproject.toml` or `src/roamer/`.
  - Connection: Not applicable
  - Client: Not applicable

**File Storage:**
- Local filesystem only. The app writes snapshots and audio files to caller-provided paths or temporary files from `tempfile.mkstemp()` in `src/roamer/capabilities/listen.py`, `src/roamer/capabilities/speak.py`, and `/tmp/roamer_snap_*` paths in `src/roamer/capabilities/watch.py`.

**Caching:**
- None. Driver objects cache in-memory model/session handles in `src/roamer/drivers/speech/asr/funasr.py` and `src/roamer/drivers/speech/vad/silero.py`, but no external cache service is used.

## Authentication & Identity

**Auth Provider:**
- None. The CLI has no user authentication, no identity provider, and no token handling under `src/roamer/`.
  - Implementation: local command execution only through `src/roamer/cli.py`

## Monitoring & Observability

**Error Tracking:**
- None. No Sentry, OpenTelemetry, or external error service is configured in `pyproject.toml` or `src/roamer/`.

**Logs:**
- Structured command responses are emitted as JSON by `output_json()` in `src/roamer/cli.py` using helpers from `src/roamer/output.py`.
- Debug traces for listen/VAD paths go to stderr via `print(..., file=sys.stderr)` in `src/roamer/capabilities/listen.py` and `src/roamer/drivers/speech/vad/silero.py`.

## CI/CD & Deployment

**Hosting:**
- Not applicable for a local CLI package. The executable entry point is `roamer = "roamer.cli:main"` in `pyproject.toml`.

**CI Pipeline:**
- None detected. No GitHub Actions, GitLab CI, CircleCI, or similar config files are present in the repository.

## Environment Configuration

**Required env vars:**
- None detected in repository code. Runtime setup is configuration-file driven through `src/roamer/cli.py` and `src/roamer/config.py`.
- Critical config keys are file-based rather than env-based:
  - `drivers.*` in `src/roamer/config.py`
  - `bluetooth.speaker_mac` in `config.example.yaml`
  - `fswebcam.device`, `alsa.capture_device`, `alsa.playback_device`, `piper.binary`, `piper.model`, `edge.voice`, `silero.model`, and `funasr.model` in `config.example.yaml`

**Secrets location:**
- No secret store is implemented. Operational settings live in `~/.config/roamer/config.yaml`, which is loaded by `src/roamer/cli.py`.
- No `.env` files were detected in the repository root or immediate subdirectories during this analysis.

## Webhooks & Callbacks

**Incoming:**
- None. No HTTP server, webhook endpoint, or callback handler exists under `src/roamer/`.

**Outgoing:**
- None implemented as repository-owned HTTP callbacks. Networked behavior is limited to external command usage such as `edge-tts` in `src/roamer/drivers/speech/tts/edge.py` and `tailscale ip -4` in `src/roamer/capabilities/sense.py`.

---

*Integration audit: 2026-04-11*
