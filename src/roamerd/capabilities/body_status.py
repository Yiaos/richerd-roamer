"""Body/system status query surface."""

from __future__ import annotations

import os
import platform
import shutil
import socket
import time

from roamerd.events.base import JSONDict


class BodyStatus:
    def snapshot(self, *, full: bool = False) -> JSONDict:
        loadavg = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
        disk = shutil.disk_usage("/")
        data: JSONDict = {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "uptime_sec": _uptime_sec(),
            "cpu_load": [float(item) for item in loadavg],
            "disk": {"total": disk.total, "used": disk.used, "free": disk.free},
            "network": {"hostname": socket.gethostname()},
        }
        if full:
            data["memory"] = _memory_info()
            data["temperature"] = None
        return data


def _uptime_sec() -> float:
    try:
        with open("/proc/uptime") as handle:
            return float(handle.read().split()[0])
    except OSError:
        return time.monotonic()


def _memory_info() -> JSONDict:
    try:
        with open("/proc/meminfo") as handle:
            entries = {}
            for line in handle:
                key, raw = line.split(":", 1)
                entries[key] = int(raw.strip().split()[0]) * 1024
            return {
                "total": entries.get("MemTotal", 0),
                "available": entries.get("MemAvailable", 0),
            }
    except OSError:
        return {"total": 0, "available": 0}
