#!/usr/bin/env bash
# Pull Phase E facts/config backup from the Pi onto a durable host path.
# Never use /tmp for off-device retention — it evaporates.
set -euo pipefail

pi_host="${ROAMER_PI_HOST:-richerd@roamer}"
pi_backup_glob="${ROAMER_PI_BACKUP_GLOB:-/home/richerd/roamerd-phase-e-backup-*}"
host_backup_root="${ROAMER_HOST_BACKUP_ROOT:-$HOME/Backups/roamer/phase-e}"
dry_run="${ROAMER_BACKUP_PULL_DRY_RUN:-0}"

log() {
  printf '[roamerd-phase-e-backup-pull] %s\n' "$*"
}

die() {
  printf '[roamerd-phase-e-backup-pull] ERROR: %s\n' "$*" >&2
  exit 1
}

if [[ "$host_backup_root" == /tmp/* || "$host_backup_root" == /var/tmp/* ]]; then
  die "refusing host backup root under tmp: $host_backup_root"
fi

mkdir -p "$host_backup_root"
chmod 700 "$host_backup_root"

log "listing remote backups on $pi_host"
mapfile -t remote_backups < <(
  ssh -o BatchMode=yes -o ConnectTimeout=8 "$pi_host" \
    "bash -lc 'compgen -G \"$pi_backup_glob\" || true'"
)

if [[ ${#remote_backups[@]} -eq 0 || -z "${remote_backups[0]:-}" ]]; then
  die "no remote backups matched $pi_backup_glob on $pi_host. Power the Pi, run scripts/roamerd-pi-collect-phase-e-facts.sh there first."
fi

latest="${remote_backups[-1]}"
name="$(basename "$latest")"
dest="$host_backup_root/$name"

log "selected remote backup: $latest"
log "durable host destination: $dest"

rsync_flags=(-a --chmod=Du=rwx,Dgo=,Fu=rw,Fgo=)
if [[ "$dry_run" == "1" ]]; then
  rsync_flags+=(--dry-run)
  log "dry-run only (ROAMER_BACKUP_PULL_DRY_RUN=1)"
fi

rsync "${rsync_flags[@]}" "${pi_host}:${latest}/" "${dest}/"
chmod 700 "$dest" 2>/dev/null || true

log "done"
log "backup retained at: $dest"
log "do not commit this directory; it may contain secrets"
