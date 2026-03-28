# Roamer

Richerd's physical body CLI - control interface for the Roamer robot.

## Features

- **Camera**: Capture images via USB camera
- **Audio**: Record and play audio via ALSA
- **Bluetooth**: Manage Bluetooth audio devices
- **Speech**: Text-to-speech (Piper) and speech recognition (FunASR)
- **System**: Monitor system status and hardware

## Installation

```bash
pip install -e ".[dev,speech]"
```

## Usage

```bash
# Camera
roamer camera snap --output /tmp/photo.jpg

# Audio
roamer audio record --duration 5 --output /tmp/recording.wav
roamer audio play /tmp/recording.wav

# Speech
roamer speak "你好世界"
roamer listen --timeout 10

# Bluetooth
roamer bt status
roamer bt connect <device-address>

# System
roamer status
```

## Output Format

All commands return JSON:

```json
{"ok": true, "path": "/tmp/photo.jpg", "width": 1280, "height": 720}
```

Errors:

```json
{"ok": false, "error": "camera_not_found", "message": "No camera at /dev/video0"}
```

## Architecture

```
CLI Layer (cli.py)
    ↓
Capability Layer (capabilities/)
    ↓
Driver Layer (drivers/)
```

Drivers are swappable via configuration.

## License

MIT
