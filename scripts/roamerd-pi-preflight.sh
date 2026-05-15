#!/usr/bin/env bash
set -euo pipefail

repo_dir="${ROAMER_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
python_bin="${PYTHON:-python3}"
openclaw_health_url="${OPENCLAW_HEALTH_URL:-http://localhost:3000/health}"
asr_ws_url="${ASR_WS_URL:-ws://hurricane.tail33ee82.ts.net:8302/}"

log() {
  printf '[roamerd-pi-preflight] %s\n' "$*"
}

require_binary() {
  local name="$1"
  command -v "$name" >/dev/null 2>&1 || {
    printf 'missing required binary: %s\n' "$name" >&2
    return 1
  }
}

require_python_module() {
  local name="$1"
  "$python_bin" - "$name" <<'PY'
import importlib
import sys

importlib.import_module(sys.argv[1])
PY
}

log "checking OS release"
"$python_bin" - <<'PY'
from pathlib import Path

values = {}
for line in Path("/etc/os-release").read_text().splitlines():
    if "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key] = value.strip('"')

if not (values.get("ID") == "ubuntu" and values.get("VERSION_ID") == "24.04"):
    actual = f'{values.get("PRETTY_NAME", values.get("ID", "unknown"))}'
    raise SystemExit(f"Ubuntu 24.04 is required for ROS 2 Jazzy deb packages; found {actual}")
PY

log "checking Python version"
"$python_bin" --version
"$python_bin" - <<'PY'
import asyncio, pydantic  # noqa: F401
import sys

if sys.version_info < (3, 11):
    raise SystemExit("python3 >= 3.11 is required")
PY

log "checking audio/camera/bluetooth binaries"
require_binary arecord
require_binary aplay
require_binary ffmpeg
require_binary ffprobe
require_binary fswebcam
require_binary bluetoothctl
require_binary pactl

log "checking Python runtime dependencies"
require_python_module gpiod
require_python_module onnxruntime
require_python_module edge_tts
require_python_module websockets

log "checking ROS 2 Jazzy Python import"
# shellcheck disable=SC1091
source /opt/ros/jazzy/setup.bash
"$python_bin" - <<'PY'
import rclpy  # noqa: F401
PY

log "checking OpenClaw health endpoint: $openclaw_health_url"
curl --fail --silent --show-error "$openclaw_health_url" >/dev/null

log "checking ASR websocket endpoint: $asr_ws_url"
"$python_bin" - "$asr_ws_url" <<'PY'
import asyncio
import sys

from websockets.asyncio.client import connect


async def main() -> None:
    async with connect(sys.argv[1], open_timeout=5):
        return None


asyncio.run(main())
PY

log "checking local mock runtime startup"
cd "$repo_dir"
PYTHONPATH="$repo_dir/src${PYTHONPATH:+:$PYTHONPATH}" \
  "$python_bin" -m roamerd --config config/roamerd.yaml --mock-drivers status >/dev/null

log "preflight passed"
