#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${ROAMER_PHASE_E_BACKUP_DIR:-$HOME/roamerd-phase-e-backup-$timestamp}"
repo_dir="${ROAMER_REPO_DIR:-/home/richerd/worksp/richerd-roamer}"

log() {
  printf '[roamerd-pi-collect-phase-e-facts] %s\n' "$*"
}

run_capture() {
  local name="$1"
  shift
  {
    printf '$'
    printf ' %q' "$@"
    printf '\n\n'
    "$@" 2>&1 || true
  } >"$backup_dir/facts/$name.txt"
}

copy_if_exists() {
  local path="$1"
  local target="$backup_dir/files${path%/*}"
  if [ -e "$path" ]; then
    mkdir -p "$target"
    cp -a "$path" "$target/"
  fi
}

mkdir -p "$backup_dir/facts" "$backup_dir/files"
chmod 700 "$backup_dir"

log "writing Phase E backup/facts to $backup_dir"

copy_if_exists "$repo_dir/config/roamerd.yaml"
copy_if_exists "$repo_dir/config/roamerd-pi.yaml"
copy_if_exists "$repo_dir/config/roamerd.example.yaml"
copy_if_exists "/home/richerd/.config/roamer/env"
copy_if_exists "/etc/roamer/roamer.env"
copy_if_exists "/etc/systemd/system/roamer-serve.service"
copy_if_exists "/etc/systemd/system/roamer-wake.service"
copy_if_exists "/etc/systemd/system/roamer-init.service"
copy_if_exists "/etc/systemd/system/roamerd.service"

run_capture os-release cat /etc/os-release
run_capture uname uname -a
run_capture repo-status bash -lc "cd '$repo_dir' && git status -sb && git log -1 --oneline"
run_capture systemd-roamer-serve systemctl cat roamer-serve.service
run_capture systemd-roamer-wake systemctl cat roamer-wake.service
run_capture systemd-roamer-init systemctl cat roamer-init.service
run_capture systemd-roamerd systemctl cat roamerd.service
run_capture arecord arecord -l
run_capture aplay aplay -l
run_capture bluetooth-devices bluetoothctl devices
run_capture tailscale tailscale status
run_capture network ip addr
run_capture disks df -h
run_capture ros-paths bash -lc "find /opt/ros -maxdepth 2 -name setup.bash -print 2>/dev/null || true"
run_capture python python3 --version

log "done"
log "backup retained on Pi at: $backup_dir"
log "before any OS reimage, pull off-device with scripts/roamerd-phase-e-backup-pull.sh"
log "do NOT copy the backup to /tmp on the host — use a durable path (default ~/Backups/roamer/phase-e)"
