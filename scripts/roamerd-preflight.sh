#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
SOCKET_PATH="${SOCKET_PATH:-/run/roamer/roamer.sock}"

if systemctl --user is-active roamer-serve.service >/dev/null 2>&1; then
  echo "legacy roamer-serve.service is still active" >&2
  exit 1
fi

if systemctl --user is-active roamer-wake.service >/dev/null 2>&1; then
  echo "legacy roamer-wake.service is still active" >&2
  exit 1
fi

if command -v lsof >/dev/null 2>&1 && lsof -t /run/roamer/roamer.sock >/dev/null 2>&1; then
  echo "control socket already has an owner: ${SOCKET_PATH}" >&2
  exit 1
fi

"$PYTHON_BIN" -m roamerd --config config/roamerd.yaml --dry-run
"$PYTHON_BIN" -m pytest tests/roamerd/contracts_migration -q

if [ "${ROAMERD_PREFLIGHT_REQUIRE_PING:-0}" = "1" ]; then
  roamer ping
fi
