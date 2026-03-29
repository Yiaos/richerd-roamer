"""Tests for sense capability."""

from unittest.mock import MagicMock, mock_open, patch

from roamer.capabilities.sense import SenseCapability


class TestSenseCapability:
    """Tests for SenseCapability."""

    def test_status_basic(self):
        """Test basic status output."""
        cap = SenseCapability({})

        with patch.object(cap, "_get_hostname", return_value="roamer"):
            with patch.object(cap, "_get_uptime", return_value=3600.0):
                with patch.object(cap, "_get_cpu_percent", return_value=15.5):
                    with patch.object(cap, "_get_memory_info", return_value={"used_mb": 1024}):
                        with patch.object(cap, "_get_temperature", return_value=45.0):
                            with patch.object(cap, "_get_disk_info", return_value={"percent": 10}):
                                with patch.object(cap, "_get_network_info", return_value={}):
                                    result = cap.status()

        assert result["ok"] is True
        assert result["hostname"] == "roamer"
        assert result["uptime_sec"] == 3600.0
        assert result["cpu_percent"] == 15.5
        assert result["temperature_c"] == 45.0

    def test_status_full_with_hardware(self):
        """Test full status with hardware checks."""
        cap = SenseCapability({})

        with patch.object(cap, "_get_hostname", return_value="roamer"):
            with patch.object(cap, "_get_uptime", return_value=3600.0):
                with patch.object(cap, "_get_cpu_percent", return_value=15.5):
                    with patch.object(cap, "_get_memory_info", return_value={}):
                        with patch.object(cap, "_get_temperature", return_value=45.0):
                            with patch.object(cap, "_get_disk_info", return_value={}):
                                with patch.object(cap, "_get_network_info", return_value={}):
                                    with patch.object(cap, "_get_hardware_status", return_value={
                                        "camera": True,
                                        "microphone": True,
                                        "bluetooth": False,
                                    }):
                                        result = cap.status(full=True)

        assert result["ok"] is True
        assert "hardware" in result
        assert result["hardware"]["camera"] is True
        assert result["hardware"]["microphone"] is True
        assert result["hardware"]["bluetooth"] is False

    def test_get_uptime(self):
        """Test uptime reading."""
        cap = SenseCapability({})

        mock_data = "12345.67 23456.78\n"
        with patch("builtins.open", mock_open(read_data=mock_data)):
            uptime = cap._get_uptime()

        assert uptime == 12345.67

    def test_get_memory_info(self):
        """Test memory info parsing."""
        cap = SenseCapability({})

        mock_data = """MemTotal:        8000000 kB
MemFree:         1000000 kB
MemAvailable:    6000000 kB
"""
        with patch("builtins.open", mock_open(read_data=mock_data)):
            info = cap._get_memory_info()

        assert info["total_mb"] == 7812
        assert info["available_mb"] == 5859
        assert "used_mb" in info
        assert "percent" in info

    def test_get_temperature(self):
        """Test temperature reading."""
        cap = SenseCapability({})

        with patch("builtins.open", mock_open(read_data="45000\n")):
            temp = cap._get_temperature()

        assert temp == 45.0

    def test_get_disk_info(self):
        """Test disk info."""
        cap = SenseCapability({})

        mock_stat = MagicMock()
        mock_stat.f_blocks = 1000000
        mock_stat.f_frsize = 4096
        mock_stat.f_bfree = 500000

        with patch("os.statvfs", return_value=mock_stat):
            info = cap._get_disk_info()

        assert "total_gb" in info
        assert "used_gb" in info
        assert "free_gb" in info
        assert "percent" in info

    def test_check_camera(self):
        """Test camera check."""
        cap = SenseCapability({})

        with patch("pathlib.Path.exists", return_value=True):
            assert cap._check_camera() is True

        with patch("pathlib.Path.exists", return_value=False):
            assert cap._check_camera() is False

    def test_check_microphone(self):
        """Test microphone check."""
        cap = SenseCapability({})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=b"card 2: Camera [Rapoo Camera]")
            assert cap._check_microphone() is True

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=b"")
            assert cap._check_microphone() is False

    def test_get_tailscale_ip(self):
        """Test Tailscale IP retrieval."""
        cap = SenseCapability({})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=b"100.90.51.104\n",
            )
            ip = cap._get_tailscale_ip()

        assert ip == "100.90.51.104"
