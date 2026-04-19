"""Tests for motion-related config defaults and overrides."""

from pathlib import Path

from roamer.platform.config import load_config


def test_default_motion_config_present() -> None:
    config = load_config(None)

    assert config["motion"]["wait_timeout_sec"] == 300
    assert config["motion"]["poll_interval_sec"] == 2
    assert config["motion"]["arrival_tolerance"] == 150


def test_user_motion_config_overrides_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
motion:
  wait_timeout_sec: 120
  poll_interval_sec: 1
  arrival_tolerance: 80
""".strip()
    )

    config = load_config(config_path)

    assert config["motion"]["wait_timeout_sec"] == 120
    assert config["motion"]["poll_interval_sec"] == 1
    assert config["motion"]["arrival_tolerance"] == 80
