"""Static checks for roamer serve systemd/socket configuration."""

from pathlib import Path

import yaml

from roamer.platform.config import DEFAULT_CONFIG


def test_systemd_socket_matches_default_config() -> None:
    service = Path("systemd/roamer-serve.service").read_text()
    config = yaml.safe_load(Path("config.yaml").read_text())
    socket_path = config["serve"]["socket"]

    assert DEFAULT_CONFIG["serve"]["socket"] == socket_path
    assert f"--socket {socket_path}" not in service
    assert "roamer serve --prepare" in service
    assert "--prewarm" not in service
    assert "playback.lock" not in service
    assert "RuntimeDirectory=" not in service
    assert "UMask=0077" in service


def test_wake_systemd_does_not_own_shared_runtime_directory() -> None:
    service = Path("systemd/roamer-wake.service").read_text()

    assert "roamer wake" in service
    assert "playback.lock" not in service
    assert "RuntimeDirectory=" not in service
    assert "UMask=0077" in service


def test_installer_creates_shared_runtime_directory() -> None:
    install = Path("install.sh").read_text()

    assert "runtime_dir=" in install
    assert "systemd-tmpfiles --create" in install
    assert "/etc/tmpfiles.d/roamer.conf" in install
