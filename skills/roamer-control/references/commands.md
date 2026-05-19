# Roamer Command Reference

## Current status

- `watch`, `speak`, `sense` are usable.
- `listen` exists but still needs real-world tuning for USB/audio-device enumeration and VAD threshold stability.
- `init` owns startup initialization such as Bluetooth speaker connection.
- `motion` is Valetudo-backed base mobility for the Roborock S5: `status`, `position`, `locate`, `home`, `goto`.
- Current `master` only documents raw-coordinate `goto`; executable named-point navigation may exist on an active branch/runtime, but should not be assumed unless that branch/runtime explicitly supports it.

## Output contract

Default output is JSON.

- Success: inspect `ok: true` plus command-specific fields.
- Failure: inspect `ok: false`, `error_code`, and `message`.
- Exception: `roamer listen --text-only` emits plain text for shell pipelines.

## Core commands

```bash
roamer watch --output /tmp/roamer.jpg
roamer speak "你好，Richer" --style cheerful
roamer listen --timeout 10 --debug
roamer listen --timeout 10 --text-only | roamer speak --stdin --prefix "我听到的是："
roamer sense --full
roamer init
```

## Motion commands

```bash
roamer motion status
roamer motion position
roamer motion locate
roamer motion home --wait
roamer motion goto --x 25500 --y 25300 --wait
roamer motion goto --x 25500 --y 25300 --angle 90 --wait
```

Named-point note:

- On current `master`, a "named place" still means manually reading `docs/valetudo-locations.md` and copying the verified coordinates into `roamer motion goto --x ... --y ...`.
- If an active branch/runtime explicitly supports executable named points, treat `motion.named_points` as the **execution source of truth** and `docs/valetudo-locations.md` as **grounding / verification evidence**.
- Config presence alone does not prove a semantic place is trustworthy; config/docs disagreement should be treated as embodiment risk, not ordinary docs drift.

Current Valetudo facts:

- Use `GET /api/v2/robot/state` for status/coordinates.
- `PUT /api/v2/robot/capabilities/BasicControlCapability {"action":"home"}` triggers docking.
- `/api/v2/map` returns 404 on the current S5, so do not rely on it.

## Utility commands

```bash
roamer audio record --duration 5 --output /tmp/rec.wav
roamer audio play /tmp/rec.wav
roamer bt status
roamer bt connect B8:5C:EE:89:00:BE
```

## Config notes

- Default config path is repo-local `config.yaml`.
- Use `-c/--config` for explicit overrides.
- If repo `config.yaml` is absent and no config is provided, Roamer falls back to internal defaults.
- Current example drivers: camera `fswebcam`, audio `alsa`, TTS `edge`, ASR `funasr`, VAD `silero`, motion `valetudo`, Bluetooth `bluez`.

## Known caveats

- PulseAudio is not the current blocker; do not describe it as such.
- Bluetooth speaker is paired but can be unstable; `speak` has lazy reconnect, `roamer init` handles boot connect, and `bt connect` is manual fallback.
- Full pytest includes hardware/model-dependent failures; use non-hardware tests for normal regression checks.
