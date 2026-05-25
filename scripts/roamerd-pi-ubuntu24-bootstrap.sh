#!/usr/bin/env bash
set -euo pipefail

repo_dir="${ROAMER_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
venv_dir="${ROAMER_VENV_DIR:-/home/richerd/.venv/roamer}"
python_bin="${PYTHON:-python3}"

log() {
  printf '[roamerd-pi-ubuntu24-bootstrap] %s\n' "$*"
}

require_install_confirmation() {
  if [ "${ROAMER_BOOTSTRAP_CONFIRM_INSTALL:-}" != "1" ]; then
    cat >&2 <<'EOF'
Set ROAMER_BOOTSTRAP_CONFIRM_INSTALL=1 to install Phase E dependencies.

This script mutates the Pi by installing Ubuntu packages, ROS 2 Jazzy deb
repositories/packages, and the project Python environment. Run it only after the
Pi has already been installed or upgraded to Ubuntu 24.04 arm64 and the Phase E
facts backup has been retained off-device.
EOF
    return 64
  fi
}

require_ubuntu_2404() {
  "$python_bin" - <<'PY'
from pathlib import Path

values = {}
for line in Path("/etc/os-release").read_text().splitlines():
    if "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key] = value.strip('"')

if not (values.get("ID") == "ubuntu" and values.get("VERSION_ID") == "24.04"):
    actual = values.get("PRETTY_NAME", values.get("ID", "unknown"))
    raise SystemExit(f"Ubuntu 24.04 is required for this bootstrap; found {actual}")
PY
}

require_install_confirmation

log "checking Ubuntu 24.04 target"
require_ubuntu_2404

log "installing base tools and runtime packages"
sudo apt update
sudo apt install -y \
  bluetooth \
  curl \
  ffmpeg \
  fswebcam \
  libgpiod-dev \
  locales \
  pulseaudio-utils \
  python3-dev \
  python3-pip \
  python3-venv \
  software-properties-common

log "ensuring UTF-8 locale and Ubuntu universe repository"
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
sudo add-apt-repository -y universe

log "installing ROS 2 Jazzy apt source"
sudo apt update
sudo apt install -y curl
ros_apt_source_version="$(
  curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest |
    grep -F '"tag_name"' |
    awk -F'"' '{print $4}'
)"
curl -L -o /tmp/ros2-apt-source.deb \
  "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ros_apt_source_version}/ros2-apt-source_${ros_apt_source_version}.$(. /etc/os-release && echo "${UBUNTU_CODENAME:-${VERSION_CODENAME}}")_all.deb"
sudo dpkg -i /tmp/ros2-apt-source.deb

log "installing ROS 2 Jazzy base and developer tools"
sudo apt update
sudo apt install -y ros-dev-tools ros-jazzy-ros-base

log "verifying ROS 2 Jazzy Python import"
# shellcheck disable=SC1091
source /opt/ros/jazzy/setup.bash
python3 - <<'PY'
import rclpy  # noqa: F401
PY

log "creating project virtual environment at $venv_dir"
python3 -m venv "$venv_dir"
cd "$repo_dir"
# shellcheck disable=SC1091
source "$venv_dir/bin/activate"
python -m pip install --upgrade pip
python -m pip install -e ".[dev,speech,gpio]"

log "running preflight with project virtual environment"
PYTHON_BIN="$venv_dir/bin/python" "$repo_dir/scripts/roamerd-preflight.sh"

log "bootstrap passed"
