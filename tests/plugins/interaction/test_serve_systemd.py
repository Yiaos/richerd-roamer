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
    assert "RuntimeDirectory=roamer" in service
    assert "RuntimeDirectoryMode=0700" in service
    assert "UMask=0077" in service
