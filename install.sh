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
venv_dir="${ROAMER_VENV:-$roamer_home/.venv/roamer}"
user_env_file="${ROAMER_ENV_FILE:-$roamer_home/.config/roamer/env}"
system_env_dir="${ROAMER_SYSTEM_ENV_DIR:-/etc/roamer}"
system_env_file="${ROAMER_SYSTEM_ENV_FILE:-$system_env_dir/roamer.env}"
service_name="${ROAMER_SERVICE_NAME:-roamer-serve.service}"
service_src="$repo_dir/systemd/roamer-serve.service"
service_dst="/etc/systemd/system/$service_name"
dropin_dir="/etc/systemd/system/$service_name.d"

[[ "$(uname -s)" == "Linux" ]] || die "install.sh must run on Roamer/Linux"
have sudo || die "sudo is required"
have systemctl || die "systemctl is required"
have python3 || die "python3 is required"
id "$roamer_user" >/dev/null 2>&1 || die "user not found: $roamer_user"

require_file "$repo_dir/pyproject.toml"
require_file "$repo_dir/config.yaml"
require_file "$service_src"
require_file "$repo_dir/scripts/init-roamer-proxy.sh"
require_dir "$roamer_home"

if [[ ! -f "$user_env_file" ]]; then
  die "runtime env file missing: $user_env_file; create it with DISCORD_BOT_TOKEN before installing"
fi

if ! grep -Eq '^(export[[:space:]]+)?DISCORD_BOT_TOKEN=.+' "$user_env_file"; then
  die "DISCORD_BOT_TOKEN missing from $user_env_file"
fi

log "installing Python package into $venv_dir"
if [[ ! -x "$venv_dir/bin/python" ]]; then
  log "creating virtualenv at $venv_dir"
  sudo -u "$roamer_user" mkdir -p "$(dirname "$venv_dir")"
  sudo -u "$roamer_user" python3 -m venv "$venv_dir"
fi
sudo -u "$roamer_user" "$venv_dir/bin/python" -m pip install -e "$repo_dir[speech]"

if [[ ! -x "$venv_dir/bin/roamer" ]]; then
  die "roamer entrypoint missing after pip install: $venv_dir/bin/roamer"
fi

log "linking /usr/local/bin/roamer to venv entrypoint"
sudo ln -sfn "$venv_dir/bin/roamer" /usr/local/bin/roamer

log "running proxy discovery to refresh $user_env_file"
sudo -u "$roamer_user" env HOME="$roamer_home" ROAMER_ENV_FILE="$user_env_file" \
  bash "$repo_dir/scripts/init-roamer-proxy.sh" >/dev/null

for key in DISCORD_BOT_TOKEN HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy NO_PROXY no_proxy; do
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
for key in DISCORD_BOT_TOKEN HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy NO_PROXY no_proxy; do
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
EOF
sudo tee "$dropin_dir/env.conf" >/dev/null <<EOF
[Service]
EnvironmentFile=$system_env_file
EOF

log "starting $service_name"
sudo systemctl daemon-reload
sudo systemctl enable --now "$service_name" >/dev/null
sudo systemctl restart "$service_name"
systemctl is-active --quiet "$service_name" || die "$service_name is not active after restart"

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
