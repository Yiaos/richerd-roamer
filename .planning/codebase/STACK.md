# Technology Stack

**Analysis Date:** 2026-04-11

## Languages

**Primary:**
- Python 3.11+ - Application code, CLI entry point, drivers, and tests live in `src/roamer/` and `tests/`, with the interpreter requirement declared in `pyproject.toml`.

**Secondary:**
- YAML - Runtime configuration is loaded from `~/.config/roamer/config.yaml` in `src/roamer/cli.py` and merged with defaults from `src/roamer/config.py`; an example lives in `config.example.yaml`.
- Markdown - Project usage and install guidance lives in `README.md`.

## Runtime

**Environment:**
- CPython 3.11 or newer - `pyproject.toml` sets `requires-python = ">=3.11"`.
- Linux-style host environment - `src/roamer/capabilities/sense.py` reads `/proc/*`, `/sys/class/thermal/*`, and shell tools such as `iwgetid`, `tailscale`, `arecord`, and `bluetoothctl`.

**Package Manager:**
- `pip` for installation and editable development workflow - `README.md` uses `pip install -e ".[dev,speech]"`.
- Python packaging/build metadata is PEP 621 in `pyproject.toml`; wheel builds use `hatchling`.
- Lockfile: missing. No `requirements.txt`, `uv.lock`, `poetry.lock`, `Pipfile.lock`, or similar file is present in the repository root.

## Frameworks

**Core:**
- Click `>=8.0` - CLI command tree and option parsing in `src/roamer/cli.py`.
- Rich `>=13.0` - Declared in `pyproject.toml` but not referenced from files under `src/roamer/`; treat it as available but currently unused in the shipped code path.
- PyYAML `>=6.0` - YAML config loading in `src/roamer/config.py`.
- NumPy `>=1.24` - Audio normalization, resampling, and VAD preprocessing in `src/roamer/capabilities/listen.py` and `src/roamer/drivers/speech/vad/silero.py`.

**Testing:**
- Pytest `>=7.0` - Test runner configured in `pyproject.toml` and used across `tests/`.
- pytest-cov `>=4.0` - Optional coverage dependency declared in `pyproject.toml`.

**Build/Dev:**
- Hatchling - Build backend declared in `pyproject.toml`.
- Ruff `>=0.1` - Lint configuration lives in `pyproject.toml` under `[tool.ruff]` and `[tool.ruff.lint]`.

## Key Dependencies

**Critical:**
- `click>=8.0` - Every user-facing command is wired through Click in `src/roamer/cli.py`.
- `pyyaml>=6.0` - Driver selection and runtime overrides are loaded through `src/roamer/config.py`.
- `numpy>=1.24` - Required for waveform loading, float normalization, resampling, and Silero VAD inference preparation in `src/roamer/capabilities/listen.py` and `src/roamer/drivers/speech/vad/silero.py`.

**Infrastructure:**
- `torch>=2.0` and `torchaudio>=2.0` - Optional speech extras declared in `pyproject.toml`; not imported directly in the current repository code, but part of the intended speech environment.
- `funasr>=1.0` - Optional ASR backend loaded dynamically in `src/roamer/drivers/speech/asr/funasr.py`.
- `onnxruntime>=1.15` - Optional inference runtime loaded dynamically in `src/roamer/drivers/speech/vad/silero.py`.

## Configuration

**Environment:**
- Runtime configuration is file-based, not env-var based. `src/roamer/cli.py` loads `~/.config/roamer/config.yaml` by default when `--config` is not provided.
- Defaults live in `src/roamer/config.py`. Supported top-level config sections shown in `config.example.yaml` include `drivers`, `bluetooth`, `fswebcam`, `alsa`, `piper`, `edge`, `silero`, `funasr`, and `valetudo`.
- Driver resolution is dynamic through `src/roamer/drivers/registry.py`, with concrete implementations under `src/roamer/drivers/audio/`, `src/roamer/drivers/bluetooth/`, `src/roamer/drivers/camera/`, and `src/roamer/drivers/speech/`.

**Build:**
- `pyproject.toml` is the single build, dependency, lint, and pytest configuration file.
- No Docker, CI, Node, frontend build, or infrastructure-as-code config files are detected in the repository root.

## Platform Requirements

**Development:**
- Python 3.11+ with editable install support from `pyproject.toml`.
- Local Linux command-line tools are part of the effective runtime surface:
  - `fswebcam` for camera capture in `src/roamer/drivers/camera/fswebcam.py`
  - `arecord` and `aplay` for ALSA audio in `src/roamer/drivers/audio/alsa.py`
  - `bluetoothctl` for BlueZ control in `src/roamer/drivers/bluetooth/bluez.py`
  - `pactl` for Bluetooth sink detection in `src/roamer/capabilities/speak.py`
  - `edge-tts`, `ffmpeg`, and `ffprobe` for cloud TTS and audio conversion in `src/roamer/drivers/speech/tts/edge.py`
- Optional local assets are expected for offline speech paths:
  - Piper binary/model paths in `src/roamer/config.py` and `config.example.yaml`
  - Silero ONNX model path in `src/roamer/config.py` and `config.example.yaml`

**Production:**
- Deployment target is a local machine or robot host running the `roamer` CLI entry point declared in `pyproject.toml`.
- No web server, background worker, cloud deployment descriptor, or database service is implemented under `src/roamer/`.

---

*Stack analysis: 2026-04-11*
