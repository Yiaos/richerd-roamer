#!/usr/bin/env bash
set -euo pipefail

systemctl --user stop roamer-serve.service roamer-wake.service 2>/dev/null || true
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
"$PYTHON_BIN" -m roamerd --config config/roamerd-pi.yaml --dry-run
ROAMERD_PREFLIGHT_REQUIRE_PING=0 scripts/roamerd-preflight.sh
systemctl --user start roamerd.service
roamer ping
