"""Tests for perception.sense action."""

from unittest.mock import MagicMock, mock_open, patch

from roamer.plugins.perception.actions.sense import SenseAction


class TestSenseAction:
    """Tests for SenseAction."""

    def test_run_basic(self):
        """Test basic status output."""
        action = SenseAction({})

        with patch.object(action, "_get_hostname", return_value="roamer"):
            with patch.object(action, "_get_uptime", return_value=3600.0):
                with patch.object(action, "_get_cpu_percent", return_value=15.5):
                    with patch.object(action, "_get_memory_info", return_value={"used_mb": 1024}):
                        with patch.object(action, "_get_temperature", return_value=45.0):
                            with patch.object(
                                action,
                                "_get_disk_info",
                                return_value={"percent": 10},
                            ):
                                with patch.object(action, "_get_network_info", return_value={}):
                                    result = action.run()

        assert result["ok"] is True
        assert result["hostname"] == "roamer"
        assert result["uptime_sec"] == 3600.0
        assert result["cpu_percent"] == 15.5
        assert result["temperature_c"] == 45.0

    def test_run_full_with_hardware(self):
        """Test full status with hardware checks."""
        action = SenseAction({})

        with patch.object(action, "_get_hostname", return_value="roamer"):
            with patch.object(action, "_get_uptime", return_value=3600.0):
                with patch.object(action, "_get_cpu_percent", return_value=15.5):
                    with patch.object(action, "_get_memory_info", return_value={}):
                        with patch.object(action, "_get_temperature", return_value=45.0):
                            with patch.object(action, "_get_disk_info", return_value={}):
                                with patch.object(action, "_get_network_info", return_value={}):
                                    with patch.object(
                                        action,
                                        "_get_hardware_status",
                                        return_value={
                                            "camera": True,
                                            "microphone": True,
                                            "bluetooth": False,
                                        },
                                    ):
                                        result = action.run(full=True)

        assert result["ok"] is True
        assert "hardware" in result
        assert result["hardware"]["camera"] is True
        assert result["hardware"]["microphone"] is True
        assert result["hardware"]["bluetooth"] is False

    def test_get_uptime(self):
        """Test uptime reading."""
        action = SenseAction({})

        mock_data = "12345.67 23456.78\n"
        with patch("builtins.open", mock_open(read_data=mock_data)):
            uptime = action._get_uptime()

        assert uptime == 12345.67

    def test_get_memory_info(self):
        """Test memory info parsing."""
        action = SenseAction({})

        mock_data = """MemTotal:        8000000 kB
MemFree:         1000000 kB
MemAvailable:    6000000 kB
"""
        with patch("builtins.open", mock_open(read_data=mock_data)):
            info = action._get_memory_info()

        assert info["total_mb"] == 7812
        assert info["available_mb"] == 5859
        assert "used_mb" in info
        assert "percent" in info

    def test_get_temperature(self):
        """Test temperature reading."""
        action = SenseAction({})

        with patch("builtins.open", mock_open(read_data="45000\n")):
            temp = action._get_temperature()

        assert temp == 45.0

    def test_get_disk_info(self):
        """Test disk info."""
        action = SenseAction({})

        mock_stat = MagicMock()
        mock_stat.f_blocks = 1000000
        mock_stat.f_frsize = 4096
        mock_stat.f_bfree = 500000

        with patch("os.statvfs", return_value=mock_stat):
            info = action._get_disk_info()

        assert "total_gb" in info
        assert "used_gb" in info
        assert "free_gb" in info
        assert "percent" in info

    def test_check_camera(self):
        """Test camera check."""
        action = SenseAction({})

        with patch("pathlib.Path.exists", return_value=True):
            assert action._check_camera() is True

        with patch("pathlib.Path.exists", return_value=False):
            assert action._check_camera() is False

    def test_check_microphone(self):
        """Test microphone check."""
        action = SenseAction({})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"card 0: Device")
            assert action._check_microphone() is True

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"")
            assert action._check_microphone() is False

    def test_check_bluetooth(self):
        """Test Bluetooth check."""
        action = SenseAction({})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"Controller XX")
            assert action._check_bluetooth() is True

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=b"")
            assert action._check_bluetooth() is False


def test_perception_plugin_registers_sense_action() -> None:
    """Plugin register() wires sense action into registry."""
    from roamer.platform.plugin_registry import PluginRegistry
    from roamer.plugins.perception.plugin import register

    registry = PluginRegistry()

    register(registry, config={})
    registered = registry.list_actions()

    assert "sense" in registered
