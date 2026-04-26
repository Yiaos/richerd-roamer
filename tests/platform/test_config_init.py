"""Tests for init-related config defaults and merges."""

from pathlib import Path

from roamer.platform.config import default_proxy_init_script_path, load_config


def test_default_init_config_present(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ROAMER_CONFIG", raising=False)
    monkeypatch.setattr(
        "roamer.platform.config.default_repo_config_path",
        lambda: tmp_path / "missing-repo.yaml",
    )

    config = load_config(None)

    assert config["init"]["connect_speaker_on_startup"] is False
    assert config["init"]["configure_proxy_on_startup"] is False
    assert config["init"]["proxy_init_script"] == str(default_proxy_init_script_path())
    assert config["init"]["proxy_init_timeout_sec"] == 20.0
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
  configure_proxy_on_startup: true
  proxy_init_script: /tmp/proxy-init.sh
  proxy_init_timeout_sec: 3.0
  bluetooth_controller_ready_timeout_sec: 9.0
  bluetooth_connect_retry_timeout_sec: 11.0
  bluetooth_retry_interval_sec: 0.5
bluetooth:
  speaker_mac: 'AA:BB:CC:DD:EE:FF'
""".strip()
    )

    config = load_config(config_path)

    assert config["init"]["connect_speaker_on_startup"] is True
    assert config["init"]["configure_proxy_on_startup"] is True
    assert config["init"]["proxy_init_script"] == "/tmp/proxy-init.sh"
    assert config["init"]["proxy_init_timeout_sec"] == 3.0
    assert config["init"]["bluetooth_controller_ready_timeout_sec"] == 9.0
    assert config["init"]["bluetooth_connect_retry_timeout_sec"] == 11.0
    assert config["init"]["bluetooth_retry_interval_sec"] == 0.5
    assert config["bluetooth"]["speaker_mac"] == "AA:BB:CC:DD:EE:FF"
