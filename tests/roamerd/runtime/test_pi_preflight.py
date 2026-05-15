from pathlib import Path
from stat import S_IXUSR


def test_pi_preflight_script_covers_phase_e_dependency_checklist() -> None:
    script_path = Path("scripts/roamerd-pi-preflight.sh")
    script = script_path.read_text()
    mode = script_path.stat().st_mode

    assert mode & S_IXUSR
    assert 'python_bin="${PYTHON:-python3}"' in script
    assert '"$python_bin" --version' in script
    assert "checking OS release" in script
    assert 'values.get("ID") == "ubuntu"' in script
    assert 'values.get("VERSION_ID") == "24.04"' in script
    assert "Ubuntu 24.04" in script
    assert "import asyncio, pydantic" in script
    for binary in ("arecord", "aplay", "ffmpeg", "ffprobe", "fswebcam", "bluetoothctl", "pactl"):
        assert f"require_binary {binary}" in script
    for module in ("gpiod", "onnxruntime", "edge_tts", "websockets"):
        assert f"require_python_module {module}" in script
    assert "source /opt/ros/jazzy/setup.bash" in script
    assert "import rclpy" in script
    assert "OPENCLAW_HEALTH_URL" in script
    assert "ASR_WS_URL" in script
    assert 'PYTHONPATH="$repo_dir/src${PYTHONPATH:+:$PYTHONPATH}"' in script
    assert '"$python_bin" -m roamerd --config config/roamerd.yaml --mock-drivers status' in script


def test_readme_documents_roamerd_phase_e_os_target() -> None:
    readme = Path("README.md").read_text()

    assert "Pi OS target for Phase E is Ubuntu 24.04" in readme
    assert "ROS 2 Jazzy deb packages" in readme
    assert "Debian 13" in readme
    assert "scripts/roamerd-pi-collect-phase-e-facts.sh" in readme


def test_phase_e_facts_collector_is_non_destructive() -> None:
    script_path = Path("scripts/roamerd-pi-collect-phase-e-facts.sh")
    script = script_path.read_text()
    mode = script_path.stat().st_mode

    assert mode & S_IXUSR
    for expected in (
        "config.yaml",
        "/home/richerd/.config/roamer/env",
        "/etc/roamer/roamer.env",
        "systemctl cat",
        "arecord -l",
        "aplay -l",
        "bluetoothctl devices",
        "tailscale status",
    ):
        assert expected in script
    for forbidden in ("mkfs", "dd ", "parted", "apt install", "reboot", "shutdown"):
        assert forbidden not in script


def test_phase_e_acceptance_runner_requires_explicit_live_confirmation() -> None:
    script_path = Path("scripts/roamerd-pi-phase-e-acceptance.sh")
    script = script_path.read_text()
    mode = script_path.stat().st_mode

    assert mode & S_IXUSR
    assert "ROAMER_ACCEPTANCE_CONFIRM_LIVE:-" in script
    assert "scripts/roamerd-pi-preflight.sh" in script
    assert "source /opt/ros/jazzy/setup.bash" in script
    assert "import rclpy" in script
    assert "colcon build" in script
    for expected in (
        "arecord -l",
        "aplay -l",
        "fswebcam",
        "bluetoothctl devices",
        "python -m roamerd --config",
        "status",
        "health",
        "sense --full",
        "watch",
        "listen",
        "speak",
        "motion status",
    ):
        assert expected in script
    for forbidden in ("mkfs", "dd ", "parted", "apt install", "reboot", "shutdown"):
        assert forbidden not in script


def test_ubuntu24_bootstrap_requires_confirmation_and_matches_ros2_target() -> None:
    script_path = Path("scripts/roamerd-pi-ubuntu24-bootstrap.sh")
    script = script_path.read_text()
    mode = script_path.stat().st_mode

    assert mode & S_IXUSR
    assert "ROAMER_BOOTSTRAP_CONFIRM_INSTALL:-" in script
    assert 'values.get("ID") == "ubuntu"' in script
    assert 'values.get("VERSION_ID") == "24.04"' in script
    assert "ros2-apt-source" in script
    assert "ros-jazzy-ros-base" in script
    assert "ros-dev-tools" in script
    assert "python3 -m venv" in script
    assert "python -m pip install -e" in script
    assert "scripts/roamerd-pi-preflight.sh" in script
    assert "source /opt/ros/jazzy/setup.bash" in script
    assert "import rclpy" in script
    for forbidden in ("mkfs", "dd ", "parted", "reboot", "shutdown"):
        assert forbidden not in script
