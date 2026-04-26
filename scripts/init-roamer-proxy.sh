#!/usr/bin/env bash
set -euo pipefail

# Auto-detect a usable HTTP(S) proxy for Roamer.
#
# Strategy:
#   1. Build LAN candidates and prefer hosts with port 7890 open.
#   2. If no LAN proxy works, probe online Tailscale peers on port 7890.
#   3. Write the first working proxy to the Roamer env file, or fail loudly.

PORT="${ROAMER_PROXY_PORT:-7890}"
ENV_FILE="${ROAMER_ENV_FILE:-$HOME/.config/roamer/env}"
TEST_URL="${ROAMER_PROXY_TEST_URL:-https://discord.com/api/v10/gateway}"
CONNECT_TIMEOUT="${ROAMER_PROXY_CONNECT_TIMEOUT:-2}"
MAX_TIME="${ROAMER_PROXY_MAX_TIME:-5}"
FULL_SWEEP="${ROAMER_PROXY_FULL_SWEEP:-0}"
NO_PROXY_VALUE="${ROAMER_NO_PROXY:-localhost,127.0.0.1,::1,10.0.0.0/8,100.64.0.0/10,.local}"

log() { printf '[roamer-proxy-init] %s\n' "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }

normalize_candidates() {
  awk 'NF && !seen[$0]++'
}

is_port_open() {
  local host="$1"
  if have nc; then
    nc -z -w 1 "$host" "$PORT" >/dev/null 2>&1
    return $?
  fi
  # Fallback for minimal systems without nc: an actual proxy probe is also a port-open test.
  probe_proxy "$host" >/dev/null 2>&1
}

probe_proxy() {
  local host="$1"
  local proxy="http://${host}:${PORT}"
  if curl -fsS --noproxy '' --connect-timeout "$CONNECT_TIMEOUT" --max-time "$MAX_TIME" -x "$proxy" "$TEST_URL" >/dev/null 2>&1; then
    printf '%s\n' "$proxy"
    return 0
  fi
  return 1
}

lan_prefixes() {
  if have ip; then
    ip -o -4 addr show scope global 2>/dev/null \
      | awk '{print $4}' \
      | cut -d/ -f1 \
      | awk -F. 'NF==4 && !($1 == 100 && $2 >= 64 && $2 <= 127) {print $1"."$2"."$3"."}'
  fi
}

seed_lan_candidates() {
  # Explicit override comes first, useful for deterministic bootstrapping.
  if [[ -n "${ROAMER_PROXY_CANDIDATES:-}" ]]; then
    printf '%s\n' $ROAMER_PROXY_CANDIDATES
  fi

  # Default gateway is commonly the always-on proxy/router candidate.
  if have ip; then
    ip route 2>/dev/null | awk '/^default / {print $3}'
    ip neigh show 2>/dev/null | awk '$1 ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/ {print $1}'
  fi

  local prefix
  for prefix in $(lan_prefixes); do
    # Prioritize known/likely always-on machines before any wider sweep.
    for last in 1 2 10 100 187 224 225 226; do
      printf '%s%s\n' "$prefix" "$last"
    done
  done
}

full_lan_sweep_candidates() {
  [[ "$FULL_SWEEP" == "1" ]] || return 0
  local prefix
  for prefix in $(lan_prefixes); do
    seq 1 254 | awk -v p="$prefix" '{print p $1}'
  done
}

lan_port_open_candidates() {
  local candidates
  candidates="$( { seed_lan_candidates; full_lan_sweep_candidates; } | normalize_candidates )"

  local host
  while IFS= read -r host; do
    [[ -n "$host" ]] || continue
    if is_port_open "$host"; then
      printf '%s\n' "$host"
    fi
  done <<< "$candidates"
}

tailscale_candidates() {
  if have tailscale; then
    tailscale status --json 2>/dev/null \
      | python3 -c 'import json,sys
try:
    data=json.load(sys.stdin)
except Exception:
    sys.exit(0)
for peer in (data.get("Peer") or {}).values():
    if peer.get("Online") is False:
        continue
    for ip in peer.get("TailscaleIPs") or []:
        if ":" not in ip:
            print(ip)' 2>/dev/null || true
  fi
}

tailscale_port_open_candidates() {
  local host
  while IFS= read -r host; do
    [[ -n "$host" ]] || continue
    if is_port_open "$host"; then
      printf '%s\n' "$host"
    fi
  done < <(tailscale_candidates | normalize_candidates)
}

write_proxy_env() {
  local proxy="$1"
  mkdir -p "$(dirname "$ENV_FILE")"
  touch "$ENV_FILE"
  chmod 600 "$ENV_FILE"

  local tmp
  tmp="$(mktemp)"
  grep -vE '^(export )?(HTTP_PROXY|HTTPS_PROXY|ALL_PROXY|http_proxy|https_proxy|all_proxy|NO_PROXY|no_proxy)=' "$ENV_FILE" > "$tmp" || true
  {
    cat "$tmp"
    printf 'export HTTP_PROXY=%q\n' "$proxy"
    printf 'export HTTPS_PROXY=%q\n' "$proxy"
    printf 'export ALL_PROXY=%q\n' "$proxy"
    printf 'export http_proxy=%q\n' "$proxy"
    printf 'export https_proxy=%q\n' "$proxy"
    printf 'export all_proxy=%q\n' "$proxy"
    printf 'export NO_PROXY=%q\n' "$NO_PROXY_VALUE"
    printf 'export no_proxy=%q\n' "$NO_PROXY_VALUE"
  } > "$ENV_FILE"
  rm -f "$tmp"
  chmod 600 "$ENV_FILE"
}

find_proxy() {
  local host proxy
  log "probing LAN hosts with open port ${PORT}"
  while IFS= read -r host; do
    [[ -n "$host" ]] || continue
    log "LAN host ${host}:${PORT} is open; testing proxy"
    if proxy="$(probe_proxy "$host")"; then
      log "selected LAN proxy ${proxy}"
      printf '%s\n' "$proxy"
      return 0
    fi
  done < <(lan_port_open_candidates)

  log "LAN proxy probe failed; probing Tailscale peers with open port ${PORT}"
  while IFS= read -r host; do
    [[ -n "$host" ]] || continue
    log "Tailscale host ${host}:${PORT} is open; testing proxy"
    if proxy="$(probe_proxy "$host")"; then
      log "selected Tailscale proxy ${proxy}"
      printf '%s\n' "$proxy"
      return 0
    fi
  done < <(tailscale_port_open_candidates)

  return 1
}

main() {
  if ! have curl; then
    log "curl is required"
    exit 2
  fi

  local proxy
  if proxy="$(find_proxy)"; then
    write_proxy_env "$proxy"
    log "wrote proxy env to ${ENV_FILE}"
    printf '%s\n' "$proxy"
    exit 0
  fi

  log "no usable proxy found on LAN or Tailscale hosts with open port ${PORT}"
  exit 1
}

main "$@"
