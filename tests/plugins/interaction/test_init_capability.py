"""Tests for startup initialization capability."""

from unittest.mock import MagicMock, patch

from roamer.plugins.interaction.capabilities.init import InitCapability


def test_init_skips_when_disabled(sample_config) -> None:
    capability = InitCapability(sample_config)

    result = capability.init()

    assert result["ok"] is True
    assert result["initialized"] is True
    assert result["steps"] == []


def test_init_connects_speaker_when_enabled(sample_config) -> None:
    sample_config["init"] = {
        "connect_speaker_on_startup": True,
        "bluetooth_controller_ready_timeout_sec": 1.0,
        "bluetooth_connect_retry_timeout_sec": 1.0,
        "bluetooth_retry_interval_sec": 0.01,
    }
    sample_config["bluetooth"] = {"speaker_mac": "AA:BB:CC:DD:EE:FF"}

    with patch("roamer.plugins.interaction.capabilities.init.BluezDriver") as mock_driver_cls:
        mock_driver = MagicMock()
        mock_driver.status.return_value = {
            "ok": True,
            "connected_devices": [],
        }
        mock_driver.connect.return_value = {
            "ok": True,
            "address": "AA:BB:CC:DD:EE:FF",
        }
        mock_driver_cls.return_value = mock_driver

        capability = InitCapability(sample_config)
        result = capability.init()

    step = result["steps"][0]
    assert step["name"] == "bluetooth_speaker_connect"
    assert step["ok"] is True
    assert step["connected"] is True
    assert step["already_connected"] is False
    assert step["connect_attempts"] == 1


def test_init_reports_already_connected(sample_config) -> None:
    sample_config["init"] = {"connect_speaker_on_startup": True}
    sample_config["bluetooth"] = {"speaker_mac": "AA:BB:CC:DD:EE:FF"}

    with patch("roamer.plugins.interaction.capabilities.init.BluezDriver") as mock_driver_cls:
        mock_driver = MagicMock()
        mock_driver.status.return_value = {
            "ok": True,
            "connected_devices": [
                {"address": "AA:BB:CC:DD:EE:FF", "name": "Speaker"},
            ],
        }
        mock_driver_cls.return_value = mock_driver

        capability = InitCapability(sample_config)
        result = capability.init()

    step = result["steps"][0]
    assert step["ok"] is True
    assert step["already_connected"] is True
    assert step["connect_attempts"] == 0
    mock_driver.connect.assert_not_called()


def test_init_skips_when_speaker_mac_missing(sample_config) -> None:
    sample_config["init"] = {"connect_speaker_on_startup": True}
    sample_config["bluetooth"] = {}

    capability = InitCapability(sample_config)
    result = capability.init()

    step = result["steps"][0]
    assert step["ok"] is False
    assert step["skipped"] is True
    assert step["reason"] == "speaker_mac_not_configured"


def test_init_waits_for_controller_then_connects(sample_config) -> None:
    sample_config["init"] = {
        "connect_speaker_on_startup": True,
        "bluetooth_controller_ready_timeout_sec": 1.0,
        "bluetooth_connect_retry_timeout_sec": 1.0,
        "bluetooth_retry_interval_sec": 0.01,
    }
    sample_config["bluetooth"] = {"speaker_mac": "AA:BB:CC:DD:EE:FF"}

    with patch("roamer.plugins.interaction.capabilities.init.BluezDriver") as mock_driver_cls:
        mock_driver = MagicMock()
        mock_driver.status.side_effect = [
            {"ok": False, "message": "No default controller available"},
            {"ok": True, "connected_devices": []},
            {"ok": True, "connected_devices": []},
        ]
        mock_driver.connect.return_value = {"ok": True, "address": "AA:BB:CC:DD:EE:FF"}
        mock_driver_cls.return_value = mock_driver

        capability = InitCapability(sample_config)
        result = capability.init()

    step = result["steps"][0]
    assert step["ok"] is True
    assert step["waited_for_controller"] is True
    assert step["connect_attempts"] == 1


def test_init_retries_connect_until_success(sample_config) -> None:
    sample_config["init"] = {
        "connect_speaker_on_startup": True,
        "bluetooth_controller_ready_timeout_sec": 1.0,
        "bluetooth_connect_retry_timeout_sec": 1.0,
        "bluetooth_retry_interval_sec": 0.01,
    }
    sample_config["bluetooth"] = {"speaker_mac": "AA:BB:CC:DD:EE:FF"}

    with patch("roamer.plugins.interaction.capabilities.init.BluezDriver") as mock_driver_cls:
        mock_driver = MagicMock()
        mock_driver.status.side_effect = [
            {"ok": True, "connected_devices": []},
            {"ok": True, "connected_devices": []},
        ]
        mock_driver.connect.side_effect = [
            {"ok": False, "error": "bluetooth_connect_failed", "message": "try 1"},
            {"ok": True, "address": "AA:BB:CC:DD:EE:FF"},
        ]
        mock_driver_cls.return_value = mock_driver

        capability = InitCapability(sample_config)
        result = capability.init()

    step = result["steps"][0]
    assert step["ok"] is True
    assert step["connect_attempts"] == 2


def test_init_fails_when_controller_never_ready(sample_config) -> None:
    sample_config["init"] = {
        "connect_speaker_on_startup": True,
        "bluetooth_controller_ready_timeout_sec": 0.02,
        "bluetooth_connect_retry_timeout_sec": 0.02,
        "bluetooth_retry_interval_sec": 0.01,
    }
    sample_config["bluetooth"] = {"speaker_mac": "AA:BB:CC:DD:EE:FF"}

    with patch("roamer.plugins.interaction.capabilities.init.BluezDriver") as mock_driver_cls:
        mock_driver = MagicMock()
        mock_driver.status.return_value = {
            "ok": False,
            "message": "No default controller available",
        }
        mock_driver_cls.return_value = mock_driver

        capability = InitCapability(sample_config)
        result = capability.init()

    step = result["steps"][0]
    assert step["ok"] is False
    assert step["error"] == "bluetooth_controller_not_ready"
    assert step["error_code"] == "bluetooth.controller.unavailable"


def test_init_runs_proxy_init_when_enabled(sample_config, tmp_path) -> None:
    script = tmp_path / "init-proxy.sh"
    script.write_text("#!/usr/bin/env bash\necho http://10.0.0.224:7890\n")
    script.chmod(0o755)
    sample_config["init"] = {
        "configure_proxy_on_startup": True,
        "proxy_init_script": str(script),
        "proxy_init_timeout_sec": 1.0,
    }

    capability = InitCapability(sample_config)
    result = capability.init()

    step = result["steps"][0]
    assert step["name"] == "proxy_init"
    assert step["ok"] is True
    assert step["proxy"] == "http://10.0.0.224:7890"
    assert step["exit_code"] == 0


def test_init_fails_when_proxy_init_script_missing(sample_config, tmp_path) -> None:
    sample_config["init"] = {
        "configure_proxy_on_startup": True,
        "proxy_init_script": str(tmp_path / "missing.sh"),
    }

    capability = InitCapability(sample_config)
    result = capability.init()

    assert result["ok"] is False
    assert result["initialized"] is False
    assert result["error"] == "proxy_init_failed"
    step = result["steps"][0]
    assert step["name"] == "proxy_init"
    assert step["ok"] is False
    assert step["skipped"] is True
    assert step["reason"] == "proxy_init_script_not_found"


def test_init_fails_when_proxy_init_command_fails(sample_config, tmp_path) -> None:
    script = tmp_path / "init-proxy.sh"
    script.write_text("#!/usr/bin/env bash\necho nope >&2\nexit 7\n")
    script.chmod(0o755)
    sample_config["init"] = {
        "configure_proxy_on_startup": True,
        "proxy_init_script": str(script),
        "proxy_init_timeout_sec": 1.0,
        "connect_speaker_on_startup": True,
    }
    sample_config["bluetooth"] = {"speaker_mac": "AA:BB:CC:DD:EE:FF"}

    capability = InitCapability(sample_config)
    result = capability.init()

    assert result["ok"] is False
    assert result["initialized"] is False
    assert result["error_code"] == "proxy.init.failed"
    assert len(result["steps"]) == 1
    assert result["steps"][0]["exit_code"] == 7
    assert result["steps"][0]["error"] == "proxy_init_failed"


def test_init_reports_active_serve_when_enabled(sample_config) -> None:
    sample_config["init"] = {"ensure_serve_on_startup": True}

    with patch("roamer.plugins.interaction.capabilities.init.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""
        capability = InitCapability(sample_config)
        result = capability.init()

    step = result["steps"][0]
    assert step["name"] == "serve_init"
    assert step["ok"] is True
    assert step["already_active"] is True
    mock_run.assert_called_once()


def test_init_starts_serve_when_inactive(sample_config) -> None:
    sample_config["init"] = {"ensure_serve_on_startup": True}

    inactive = MagicMock(returncode=3, stdout="", stderr="")
    started = MagicMock(returncode=0, stdout="started", stderr="")
    with patch(
        "roamer.plugins.interaction.capabilities.init.subprocess.run",
        side_effect=[inactive, started],
    ):
        capability = InitCapability(sample_config)
        result = capability.init()

    step = result["steps"][0]
    assert step["name"] == "serve_init"
    assert step["ok"] is True
    assert step["already_active"] is False
    assert step["stdout"] == "started"


def test_init_structures_systemd_unavailable(sample_config) -> None:
    sample_config["init"] = {"ensure_serve_on_startup": True}

    with patch(
        "roamer.plugins.interaction.capabilities.init.subprocess.run",
        side_effect=OSError("no systemctl"),
    ):
        capability = InitCapability(sample_config)
        result = capability.init()

    step = result["steps"][0]
    assert step["name"] == "serve_init"
    assert step["ok"] is False
    assert step["skipped"] is True
    assert step["reason"] == "systemd_unavailable"


def test_init_fails_top_level_when_serve_start_fails(sample_config) -> None:
    sample_config["init"] = {"ensure_serve_on_startup": True}

    inactive = MagicMock(returncode=3, stdout="", stderr="")
    failed = MagicMock(returncode=1, stdout="", stderr="boom")
    with patch(
        "roamer.plugins.interaction.capabilities.init.subprocess.run",
        side_effect=[inactive, failed],
    ):
        capability = InitCapability(sample_config)
        result = capability.init()

    assert result["ok"] is False
    assert result["initialized"] is False
    assert result["error_code"] == "serve.unavailable"
    assert result["steps"][0]["name"] == "serve_init"
    assert result["steps"][0]["error"] == "serve_start_failed"
