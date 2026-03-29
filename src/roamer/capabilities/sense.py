"""Sense capability - self-state perception."""

import os
import socket
import subprocess
from pathlib import Path
from typing import Any

from roamer.capabilities.base import Capability
from roamer.output import success


class SenseCapability(Capability):
    """Sense capability - perceive self-state and environment."""

    def status(self, full: bool = False) -> dict[str, Any]:
        """Get system status.

        Args:
            full: Include hardware checks

        Returns:
            Result dict with system information
        """
        result = {
            "hostname": self._get_hostname(),
            "uptime_sec": self._get_uptime(),
            "cpu_percent": self._get_cpu_percent(),
            "memory": self._get_memory_info(),
            "temperature_c": self._get_temperature(),
            "disk": self._get_disk_info(),
            "network": self._get_network_info(),
        }

        if full:
            result["hardware"] = self._get_hardware_status()

        return success(**result)

    def _get_hostname(self) -> str:
        """Get system hostname."""
        return socket.gethostname()

    def _get_uptime(self) -> float | None:
        """Get system uptime in seconds."""
        try:
            with open("/proc/uptime") as f:
                return float(f.read().split()[0])
        except Exception:
            return None

    def _get_cpu_percent(self) -> float | None:
        """Get CPU usage percentage."""
        try:
            with open("/proc/stat") as f:
                line = f.readline()

            parts = line.split()
            if parts[0] != "cpu":
                return None

            user = int(parts[1])
            nice = int(parts[2])
            system = int(parts[3])
            idle = int(parts[4])

            total = user + nice + system + idle
            used = user + nice + system

            return round(used / total * 100, 1) if total > 0 else None
        except Exception:
            return None

    def _get_memory_info(self) -> dict[str, Any]:
        """Get memory information."""
        try:
            with open("/proc/meminfo") as f:
                lines = f.readlines()

            info = {}
            for line in lines:
                parts = line.split()
                if parts[0] == "MemTotal:":
                    info["total_mb"] = int(parts[1]) // 1024
                elif parts[0] == "MemAvailable:":
                    info["available_mb"] = int(parts[1]) // 1024

            if "total_mb" in info and "available_mb" in info:
                info["used_mb"] = info["total_mb"] - info["available_mb"]
                info["percent"] = round(info["used_mb"] / info["total_mb"] * 100, 1)

            return info
        except Exception:
            return {}

    def _get_temperature(self) -> float | None:
        """Get CPU temperature in Celsius."""
        thermal_paths = [
            "/sys/class/thermal/thermal_zone0/temp",
            "/sys/devices/virtual/thermal/thermal_zone0/temp",
        ]

        for path in thermal_paths:
            try:
                with open(path) as f:
                    temp = int(f.read().strip())
                    return temp / 1000.0
            except Exception:
                continue

        return None

    def _get_disk_info(self) -> dict[str, Any]:
        """Get disk usage information."""
        try:
            stat = os.statvfs("/")
            total = stat.f_blocks * stat.f_frsize
            free = stat.f_bfree * stat.f_frsize
            used = total - free

            return {
                "total_gb": round(total / (1024**3), 1),
                "used_gb": round(used / (1024**3), 1),
                "free_gb": round(free / (1024**3), 1),
                "percent": round(used / total * 100, 1) if total > 0 else 0,
            }
        except Exception:
            return {}

    def _get_network_info(self) -> dict[str, Any]:
        """Get network information."""
        info: dict[str, Any] = {}

        wifi_info = self._get_wifi_info()
        if wifi_info:
            info.update(wifi_info)

        tailscale_ip = self._get_tailscale_ip()
        if tailscale_ip:
            info["tailscale_ip"] = tailscale_ip

        return info

    def _get_wifi_info(self) -> dict[str, Any] | None:
        """Get Wi-Fi connection information."""
        try:
            result = subprocess.run(
                ["iwgetid", "-r"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                ssid = result.stdout.decode().strip()
                if ssid:
                    info: dict[str, Any] = {"wifi_ssid": ssid}

                    signal = self._get_wifi_signal()
                    if signal is not None:
                        info["wifi_signal_dbm"] = signal

                    return info
        except Exception:
            pass

        return None

    def _get_wifi_signal(self) -> int | None:
        """Get Wi-Fi signal strength in dBm."""
        try:
            with open("/proc/net/wireless") as f:
                lines = f.readlines()

            for line in lines[2:]:
                parts = line.split()
                if len(parts) >= 4:
                    signal = int(float(parts[3]))
                    return signal
        except Exception:
            pass

        return None

    def _get_tailscale_ip(self) -> str | None:
        """Get Tailscale IP address."""
        try:
            result = subprocess.run(
                ["tailscale", "ip", "-4"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.decode().strip()
        except Exception:
            pass

        return None

    def _get_hardware_status(self) -> dict[str, bool]:
        """Check hardware availability."""
        return {
            "camera": self._check_camera(),
            "microphone": self._check_microphone(),
            "bluetooth": self._check_bluetooth(),
        }

    def _check_camera(self) -> bool:
        """Check if camera is available."""
        return Path("/dev/video0").exists()

    def _check_microphone(self) -> bool:
        """Check if microphone is available."""
        try:
            result = subprocess.run(
                ["arecord", "-l"],
                capture_output=True,
                timeout=5,
            )
            return "card" in result.stdout.decode().lower()
        except Exception:
            return False

    def _check_bluetooth(self) -> bool:
        """Check if Bluetooth is available."""
        try:
            result = subprocess.run(
                ["bluetoothctl", "show"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0 and b"Controller" in result.stdout
        except Exception:
            return False
