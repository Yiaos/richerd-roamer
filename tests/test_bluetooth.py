"""Tests for Bluetooth driver and capability."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from roamer.drivers.bluetooth.bluez import BluezDriver


class TestBluezDriver:
    """Tests for BluezDriver."""

    def test_status_success(self):
        """Test getting Bluetooth status."""
        driver = BluezDriver({})

        controller_output = b"""Controller DC:A6:32:XX:XX:XX
Name: Roamer
Powered: yes
Discoverable: no
"""
        devices_output = b"""Device F4:93:80:38:13:77 GO 3S
Device AA:BB:CC:DD:EE:FF Speaker
"""

        with patch("subprocess.run") as mock_run:
            def side_effect(cmd, **kwargs):
                if "show" in cmd:
                    return MagicMock(returncode=0, stdout=controller_output)
                elif "Connected" in cmd:
                    return MagicMock(returncode=0, stdout=devices_output)
                return MagicMock(returncode=0, stdout=b"")

            mock_run.side_effect = side_effect
            result = driver.status()

        assert result["ok"] is True
        assert result["controller"]["name"] == "Roamer"
        assert result["controller"]["powered"] is True
        assert len(result["connected_devices"]) == 2

    def test_status_no_controller(self):
        """Test status when no controller available."""
        driver = BluezDriver({})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=b"")
            result = driver.status()

        assert result["ok"] is False
        assert result["error"] == "bluetooth_not_available"

    def test_connect_success(self):
        """Test successful connection."""
        driver = BluezDriver({})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=b"Connection successful",
                stderr=b"",
            )
            result = driver.connect("AA:BB:CC:DD:EE:FF")

        assert result["ok"] is True
        assert result["connected"] is True
        assert result["address"] == "AA:BB:CC:DD:EE:FF"

    def test_connect_failure(self):
        """Test connection failure."""
        driver = BluezDriver({})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout=b"Failed to connect",
                stderr=b"",
            )
            result = driver.connect("AA:BB:CC:DD:EE:FF")

        assert result["ok"] is False
        assert result["error"] == "bluetooth_connect_failed"

    def test_connect_timeout(self):
        """Test connection timeout."""
        driver = BluezDriver({})

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="bluetoothctl", timeout=30)
            result = driver.connect("AA:BB:CC:DD:EE:FF")

        assert result["ok"] is False
        assert result["error"] == "bluetooth_connect_failed"
        assert "timed out" in result["message"]

    def test_disconnect_success(self):
        """Test successful disconnection."""
        driver = BluezDriver({})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=b"Successful disconnected",
            )
            result = driver.disconnect("AA:BB:CC:DD:EE:FF")

        assert result["ok"] is True
        assert result["disconnected"] is True


@pytest.mark.hardware
class TestBluetoothHardware:
    """Hardware tests - require actual Bluetooth."""

    def test_status_real_hardware(self):
        """Test getting real Bluetooth status."""
        driver = BluezDriver({})
        result = driver.status()
        # May or may not have controller, but should not crash
        assert "ok" in result
