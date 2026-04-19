"""Tests for init-related config defaults and merges."""

from pathlib import Path

from roamer.platform.config import load_config


def test_default_init_config_present() -> None:
    config = load_config(None)

    assert config["init"]["connect_speaker_on_startup"] is False
    assert config["init"]["bluetooth_controller_ready_timeout_sec"] == 20.0
    assert config["init"]["bluetooth_connect_retry_timeout_sec"] == 20.0
    assert config["init"]["bluetooth_retry_interval_sec"] == 1.0
    assert config["bluetooth"]["speaker_mac"] is None


def test_user_init_config_overrides_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
init:
  connect_speaker_on_startup: true
  bluetooth_controller_ready_timeout_sec: 9.0
  bluetooth_connect_retry_timeout_sec: 11.0
  bluetooth_retry_interval_sec: 0.5
bluetooth:
  speaker_mac: 'AA:BB:CC:DD:EE:FF'
""".strip()
    )

    config = load_config(config_path)

    assert config["init"]["connect_speaker_on_startup"] is True
    assert config["init"]["bluetooth_controller_ready_timeout_sec"] == 9.0
    assert config["init"]["bluetooth_connect_retry_timeout_sec"] == 11.0
    assert config["init"]["bluetooth_retry_interval_sec"] == 0.5
    assert config["bluetooth"]["speaker_mac"] == "AA:BB:CC:DD:EE:FF"
