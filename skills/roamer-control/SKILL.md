---
name: roamer-control
description: Operate and maintain Richerd's Roamer physical-body CLI. Use when the user asks about Roamer capabilities, voice output/input, camera snapshots, self-state sensing, Bluetooth/audio troubleshooting, boot initialization, Valetudo/S5 base motion, coordinates, docking, goto/navigation, or Roamer repository changes involving supported commands.
---

# Roamer Control

Roamer is Richerd's physical-body CLI. Use it to operate the Pi-mounted robot stack safely and to modify Roamer code/docs without re-discovering the current command contract.

## First decision

- For **live operation**, prefer `ssh richerd@roamer 'roamer ...'` from the host unless already running on Roamer.
- For **repo work**, use `~/worksp/richerd-roamer`.
- For **project notes**, use `~/Documents/notes/2-Project/roamer/` (`docs/` in the repo is a symlink there).
- For **motion coordinates**, read `docs/valetudo-locations.md` before using stored points.

## Live-operation rules

- Treat `speak`, `audio play`, `motion home`, `motion goto`, and `bt connect` as real-world actions.
- If the user explicitly asks for the action, execute it; otherwise ask before producing sound or moving hardware.
- Before `motion goto`, check readiness with `motion status` or `motion position` unless the user is asking for emergency/obvious return-to-dock.
- Prefer JSON output and inspect `ok`, `error_code`, and `message` before claiming success.
- Use timeouts on SSH/commands; do not leave long-running hardware commands hanging.

## Command patterns

From the host:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 richerd@roamer 'roamer sense --full'
ssh -o BatchMode=yes -o ConnectTimeout=10 richerd@roamer 'roamer speak "测试一下语音播放"'
ssh -o BatchMode=yes -o ConnectTimeout=10 richerd@roamer 'roamer watch --output /tmp/roamer.jpg'
ssh -o BatchMode=yes -o ConnectTimeout=10 richerd@roamer 'roamer motion status'
ssh -o BatchMode=yes -o ConnectTimeout=10 richerd@roamer 'roamer motion position'
ssh -o BatchMode=yes -o ConnectTimeout=10 richerd@roamer 'roamer motion home --wait'
```

Inside the repo/local dev environment:

```bash
cd ~/worksp/richerd-roamer
.venv/bin/roamer sense --full
.venv/bin/pytest -q -m 'not hardware'
.venv/bin/ruff check
```

## Capability map

Core capabilities:

- `watch` — visual perception / camera capture.
- `speak` — TTS voice output; supports positional text, `--stdin`, `--prefix`, `--style`, `--save`, `--no-play`.
- `listen` — voice input; `--text-only` is the pipeline-friendly mode.
- `sense` — self-state perception; use `--full` for hardware checks.
- `init` — Roamer-owned startup initialization.
- `motion status|position|locate|home|goto` — Valetudo-backed S5 base mobility.

Utilities:

- `audio record|play` — low-level audio troubleshooting.
- `bt status|connect` — Bluetooth speaker fallback.

See `references/commands.md` for the command catalog and current caveats.

## Motion safety workflow

1. Run `roamer motion status` or `roamer motion position`.
2. If using a named place, read `docs/valetudo-locations.md` and copy the latest verified coordinates.
3. For docking, use `roamer motion home --wait`.
4. For navigation, use `roamer motion goto --x <x> --y <y> [--angle <deg>] [--wait]`.
5. Verify result JSON; if movement fails, report the exact `error_code`/`message`.

Do not invent natural-language navigation or teleop features. Current `motion` means base mobility only: status, position, locate, home, goto.

## Development workflow

- Keep command handlers thin; implementation belongs in plugins/capabilities/drivers.
- Preserve deterministic JSON output; `listen --text-only` is the intentional exception.
- Run focused tests for changed areas, then `pytest -q -m 'not hardware'` when practical.
- Hardware-dependent full pytest failures may be pre-existing; separate hardware failures from regressions.
