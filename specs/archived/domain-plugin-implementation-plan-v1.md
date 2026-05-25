# Implementation Plan: Roamer Plugin-Centric Layout

## Overview
Stabilize a single-root codebase (`src/roamer`) with this structure:
- `roamer.cli`
- `roamer.platform`
- `roamer.domains`
- `roamer.plugins`

`shared` has been removed; reusable code now lives inside owning plugins.

## Current State
- Completed:
  - entrypoint: `roamer.cli.main:main`
  - platform primitives: config/contract/output/errors/runtime/registry
  - perception plugin actions: `watch`, `sense`
  - interaction plugin actions: `listen`, `speak`, `audio.record`, `audio.play`, `bt.status`, `bt.connect`
  - interaction plugin-local capabilities and drivers
  - tests split by concern (`tests/cli`, `tests/platform`, `tests/core`, `tests/plugins/*`)
- Next:
  - strengthen typed domain contracts in `domains/*/contracts.py`
  - add future plugins (locomotion/behavior) only when corresponding actions are introduced

## Validation Gate
- `PYTHONPATH=src .venv/bin/ruff check src tests`
- `PYTHONPATH=src .venv/bin/pytest -q -m 'not hardware'`
