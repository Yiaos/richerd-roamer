#!/usr/bin/env bash
set -euo pipefail

repo_dir="${ROAMER_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
python_bin="${PYTHON:-python3}"
config_path="${ROAMER_CONFIG:-$repo_dir/config/roamerd-pi.yaml}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
acceptance_dir="${ROAMER_ACCEPTANCE_DIR:-$HOME/roamerd-phase-e-acceptance-$timestamp}"
audio_seconds="${ROAMER_ACCEPTANCE_AUDIO_SECONDS:-3}"
listen_timeout="${ROAMER_ACCEPTANCE_LISTEN_TIMEOUT:-10}"
command_timeout="${ROAMER_ACCEPTANCE_COMMAND_TIMEOUT:-30}"

log() {
  printf '[roamerd-pi-phase-e-acceptance] %s\n' "$*"
}

require_live_confirmation() {
  if [ "${ROAMER_ACCEPTANCE_CONFIRM_LIVE:-}" != "1" ]; then
    cat >&2 <<'EOF'
Set ROAMER_ACCEPTANCE_CONFIRM_LIVE=1 to run Phase E live acceptance.

This script starts hardware-facing checks for SU-03T/ALSA/fswebcam/BlueZ/ROS2/
Valetudo through roamerd. Run it only after the Pi has Ubuntu 24.04, ROS 2 Jazzy,
restored config/secrets, and a passing scripts/roamerd-preflight.sh result.
EOF
    return 64
  fi
}

run_capture() {
  local name="$1"
  shift
  {
    printf '$'
    printf ' %q' "$@"
    printf '\n\n'
    "$@" 2>&1
  } >"$acceptance_dir/$name.txt"
}

run_shell_capture() {
  local name="$1"
  local command="$2"
  {
    printf '$ %s\n\n' "$command"
    bash -lc "$command" 2>&1
  } >"$acceptance_dir/$name.txt"
}

run_roamerd_capture() {
  local name="$1"
  shift
  {
    printf '$ python -m roamerd --config %q' "$config_path"
    printf ' %q' "$@"
    printf '\n\n'
    PYTHONPATH="$repo_dir/src${PYTHONPATH:+:$PYTHONPATH}" \
      timeout "$command_timeout" "$python_bin" -m roamerd --config "$config_path" "$@" 2>&1
  } >"$acceptance_dir/$name.txt"
}

require_live_confirmation
mkdir -p "$acceptance_dir"
chmod 700 "$acceptance_dir"

log "writing Phase E acceptance evidence to $acceptance_dir"
log "running preflight"
run_shell_capture preflight "PYTHON_BIN='$python_bin' '$repo_dir/scripts/roamerd-preflight.sh'"

log "checking ROS 2 and building roamer_ros"
run_shell_capture ros-rclpy "source /opt/ros/jazzy/setup.bash && $python_bin -c 'import rclpy'"
run_shell_capture ros-colcon-build "cd '$repo_dir/ros2_ws' && source /opt/ros/jazzy/setup.bash && colcon build"

log "capturing ALSA, Bluetooth, and camera evidence"
run_capture alsa-record-devices arecord -l
run_capture alsa-playback-devices aplay -l
run_capture bluetooth-devices bluetoothctl devices
run_capture alsa-live-capture timeout "$((audio_seconds + 5))" arecord -q -d "$audio_seconds" -f cd "$acceptance_dir/alsa-capture.wav"
run_capture camera-fswebcam timeout "$command_timeout" fswebcam "$acceptance_dir/fswebcam.jpg"

log "running real-driver roamerd finite commands through ControlBridge shim"
run_roamerd_capture runtime-status status
run_roamerd_capture body-sense sense
run_roamerd_capture vision-watch watch
run_roamerd_capture hearing-listen listen
run_roamerd_capture speech-speak speak "roamerd Phase E acceptance test"
run_roamerd_capture motion-status motion status

log "acceptance evidence captured"
