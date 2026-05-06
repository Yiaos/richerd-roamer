#!/usr/bin/env bash
set -euo pipefail

log() { printf '[roamer-install] %s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

require_file() {
  local path="$1"
  [[ -f "$path" ]] || die "required file missing: $path"
}

require_dir() {
  local path="$1"
  [[ -d "$path" ]] || die "required directory missing: $path"
}

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
roamer_user="${ROAMER_USER:-richerd}"

if ! roamer_home="$(getent passwd "$roamer_user" 2>/dev/null | cut -d: -f6)"; then
  roamer_home=""
fi
roamer_home="${ROAMER_HOME:-${roamer_home:-/home/$roamer_user}}"
roamer_uid="$(id -u "$roamer_user")"
venv_dir="${ROAMER_VENV:-$roamer_home/.venv/roamer}"
user_env_file="${ROAMER_ENV_FILE:-$roamer_home/.config/roamer/env}"
system_env_dir="${ROAMER_SYSTEM_ENV_DIR:-/etc/roamer}"
system_env_file="${ROAMER_SYSTEM_ENV_FILE:-$system_env_dir/roamer.env}"
service_name="${ROAMER_SERVICE_NAME:-roamer-serve.service}"
service_src="$repo_dir/systemd/roamer-serve.service"
service_dst="/etc/systemd/system/$service_name"
dropin_dir="/etc/systemd/system/$service_name.d"
log_dir="${ROAMER_LOG_DIR:-/var/log/roamer}"
wake_service_name="${ROAMER_WAKE_SERVICE_NAME:-roamer-wake.service}"
wake_service_src="$repo_dir/systemd/roamer-wake.service"
wake_service_dst="/etc/systemd/system/$wake_service_name"
wake_dropin_dir="/etc/systemd/system/$wake_service_name.d"
init_service_name="${ROAMER_INIT_SERVICE_NAME:-roamer-init.service}"
init_service_src="$repo_dir/systemd/roamer-init.service"
init_service_dst="/etc/systemd/system/$init_service_name"
init_dropin_dir="/etc/systemd/system/$init_service_name.d"

[[ "$(uname -s)" == "Linux" ]] || die "install.sh must run on Roamer/Linux"
have sudo || die "sudo is required"
have systemctl || die "systemctl is required"
have python3 || die "python3 is required"
id "$roamer_user" >/dev/null 2>&1 || die "user not found: $roamer_user"

require_file "$repo_dir/pyproject.toml"
require_file "$repo_dir/config.yaml"
require_file "$service_src"
require_file "$wake_service_src"
require_file "$init_service_src"
require_file "$repo_dir/scripts/init-roamer-proxy.sh"
require_dir "$roamer_home"

log "installing Python package into $venv_dir"
if [[ ! -x "$venv_dir/bin/python" ]]; then
  log "creating virtualenv at $venv_dir"
  sudo -u "$roamer_user" mkdir -p "$(dirname "$venv_dir")"
  sudo -u "$roamer_user" python3 -m venv "$venv_dir"
fi
sudo -u "$roamer_user" "$venv_dir/bin/python" -m pip install -e "$repo_dir[speech,gpio]"

if [[ ! -x "$venv_dir/bin/roamer" ]]; then
  die "roamer entrypoint missing after pip install: $venv_dir/bin/roamer"
fi

log "linking /usr/local/bin/roamer to venv entrypoint"
sudo ln -sfn "$venv_dir/bin/roamer" /usr/local/bin/roamer

log "creating runtime log directory $log_dir"
sudo install -d -m 0750 -o "$roamer_user" -g "$roamer_user" "$log_dir"

log "running proxy discovery to refresh $user_env_file"
sudo -u "$roamer_user" env HOME="$roamer_home" ROAMER_ENV_FILE="$user_env_file" \
  bash "$repo_dir/scripts/init-roamer-proxy.sh" >/dev/null

discord_enabled="$("$venv_dir/bin/python" - "$repo_dir/config.yaml" <<'PY'
import sys
import yaml

with open(sys.argv[1], encoding="utf-8") as f:
    config = yaml.safe_load(f) or {}
discord = config.get("converse", {}).get("discord", {})
print("yes" if discord.get("enabled") is True else "no")
PY
)"

required_env_keys=(HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy NO_PROXY no_proxy)
if [[ "$discord_enabled" == "yes" ]]; then
  required_env_keys=(DISCORD_BOT_TOKEN "${required_env_keys[@]}")
fi

for key in "${required_env_keys[@]}"; do
  grep -Eq "^(export[[:space:]]+)?$key=.+" "$user_env_file" || die "$key missing after proxy init"
done

log "writing systemd environment file $system_env_file"
sudo install -d -m 0750 -o root -g root "$system_env_dir"
tmp_env="$(mktemp)"
awk '
  /^(export )?(DISCORD_BOT_TOKEN|HTTP_PROXY|HTTPS_PROXY|ALL_PROXY|http_proxy|https_proxy|all_proxy|NO_PROXY|no_proxy)=/ {
    sub(/^export /, "")
    print
  }
' "$user_env_file" > "$tmp_env"
for key in "${required_env_keys[@]}"; do
  grep -Eq "^$key=.+" "$tmp_env" || die "converted systemd env is missing $key"
done
sudo install -m 0600 -o root -g root "$tmp_env" "$system_env_file"
rm -f "$tmp_env"

log "installing $service_name"
sudo install -m 0644 -o root -g root "$service_src" "$service_dst"
sudo install -d -m 0755 -o root -g root "$dropin_dir"
sudo tee "$dropin_dir/user.conf" >/dev/null <<EOF
[Service]
User=$roamer_user
Group=$roamer_user
Environment=HOME=$roamer_home
Environment=XDG_RUNTIME_DIR=/run/user/$roamer_uid
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$roamer_uid/bus
EOF
sudo tee "$dropin_dir/env.conf" >/dev/null <<EOF
[Service]
EnvironmentFile=$system_env_file
EOF

wake_enabled="$("$venv_dir/bin/python" - "$repo_dir/config.yaml" <<'PY'
import sys
import yaml

with open(sys.argv[1], encoding="utf-8") as f:
    config = yaml.safe_load(f) or {}
wakeword = config.get("converse", {}).get("wakeword", {})
print(
    "yes"
    if wakeword.get("enabled") is True and wakeword.get("driver") == "su03t_gpio"
    else "no"
)
PY
)"

init_enabled="$("$venv_dir/bin/python" - "$repo_dir/config.yaml" <<'PY'
import sys
import yaml

with open(sys.argv[1], encoding="utf-8") as f:
    config = yaml.safe_load(f) or {}
init = config.get("init", {})
keys = (
    "connect_speaker_on_startup",
    "configure_proxy_on_startup",
    "ensure_serve_on_startup",
)
print("yes" if any(init.get(key) is True for key in keys) else "no")
PY
)"

if [[ "$wake_enabled" == "yes" ]]; then
  log "verifying GPIO dependency for $wake_service_name"
  sudo -u "$roamer_user" "$venv_dir/bin/python" - <<'PY'
import gpiod  # noqa: F401
PY

  log "installing $wake_service_name"
  sudo install -m 0644 -o root -g root "$wake_service_src" "$wake_service_dst"
  sudo install -d -m 0755 -o root -g root "$wake_dropin_dir"
  sudo tee "$wake_dropin_dir/user.conf" >/dev/null <<EOF
[Service]
User=$roamer_user
Group=$roamer_user
Environment=HOME=$roamer_home
Environment=XDG_RUNTIME_DIR=/run/user/$roamer_uid
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$roamer_uid/bus
EOF
  sudo tee "$wake_dropin_dir/env.conf" >/dev/null <<EOF
[Service]
EnvironmentFile=$system_env_file
EOF
else
  log "$wake_service_name not enabled by config; disabling wake service if present"
  sudo systemctl disable --now "$wake_service_name" >/dev/null 2>&1 || true
fi

if [[ "$init_enabled" == "yes" ]]; then
  log "installing $init_service_name"
  sudo install -m 0644 -o root -g root "$init_service_src" "$init_service_dst"
  sudo install -d -m 0755 -o root -g root "$init_dropin_dir"
  sudo tee "$init_dropin_dir/user.conf" >/dev/null <<EOF
[Service]
User=$roamer_user
Group=$roamer_user
Environment=HOME=$roamer_home
Environment=XDG_RUNTIME_DIR=/run/user/$roamer_uid
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$roamer_uid/bus
EOF
  sudo tee "$init_dropin_dir/env.conf" >/dev/null <<EOF
[Service]
EnvironmentFile=$system_env_file
EOF
else
  log "$init_service_name not enabled by config; disabling init service if present"
  sudo systemctl disable --now "$init_service_name" >/dev/null 2>&1 || true
fi

log "starting $service_name"
sudo systemctl daemon-reload
sudo systemctl enable --now "$service_name" >/dev/null
sudo systemctl restart "$service_name"
systemctl is-active --quiet "$service_name" || die "$service_name is not active after restart"

if [[ "$wake_enabled" == "yes" ]]; then
  log "starting $wake_service_name"
  sudo systemctl enable --now "$wake_service_name" >/dev/null
  sudo systemctl restart "$wake_service_name"
  systemctl is-active --quiet "$wake_service_name" || die "$wake_service_name is not active after restart"
fi

if [[ "$init_enabled" == "yes" ]]; then
  log "enabling $init_service_name"
  sudo systemctl enable "$init_service_name" >/dev/null
fi

log "verifying Roamer daemon"
for _ in $(seq 1 30); do
  if "/usr/local/bin/roamer" serve ping >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
"/usr/local/bin/roamer" serve ping >/dev/null
"/usr/local/bin/roamer" serve status >/dev/null

log "installation complete"
