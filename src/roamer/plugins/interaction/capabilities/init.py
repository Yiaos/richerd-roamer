"""Startup initialization capability for Roamer-owned boot logic."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from roamer.platform.contract import ErrorCode
from roamer.platform.output import error, success
from roamer.plugins.interaction.capabilities.base import Capability
from roamer.plugins.interaction.drivers.bluetooth.bluez import BluezDriver


class InitCapability(Capability):
    """Run startup initialization owned by Roamer itself."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        bt_config = config.get("bluetooth", {})
        init_config = config.get("init", {})

        self._speaker_mac = bt_config.get("speaker_mac")
        self._configure_proxy_on_startup = bool(
            init_config.get("configure_proxy_on_startup", False)
        )
        self._proxy_init_script = str(
            init_config.get(
                "proxy_init_script",
                "scripts/init-roamer-proxy.sh",
            )
        )
        self._proxy_init_timeout_sec = float(
            init_config.get("proxy_init_timeout_sec", 20.0)
        )
        self._connect_speaker_on_startup = bool(
            init_config.get("connect_speaker_on_startup", False)
        )
        self._ensure_serve_on_startup = bool(
            init_config.get("ensure_serve_on_startup", False)
        )
        self._serve_start_timeout_sec = float(
            init_config.get("serve_start_timeout_sec", 10.0)
        )
        self._controller_ready_timeout_sec = float(
            init_config.get("bluetooth_controller_ready_timeout_sec", 20.0)
        )
        self._connect_retry_timeout_sec = float(
            init_config.get("bluetooth_connect_retry_timeout_sec", 20.0)
        )
        self._retry_interval_sec = float(
            init_config.get("bluetooth_retry_interval_sec", 1.0)
        )
        self._bluetooth = BluezDriver(config.get("bluez", {}))

    def run(self) -> dict[str, Any]:
        """Registry-compatible entrypoint."""
        return self.init()

    def init(self) -> dict[str, Any]:
        """Run boot/startup initialization tasks."""
        steps: list[dict[str, Any]] = []

        if self._configure_proxy_on_startup:
            proxy_step = self._configure_proxy_step()
            steps.append(proxy_step)
            if not proxy_step.get("ok"):
                return error(
                    "proxy_init_failed",
                    proxy_step.get("message") or "Proxy initialization failed",
                    error_code="proxy.init.failed",
                    initialized=False,
                    steps=steps,
                )

        if self._connect_speaker_on_startup:
            steps.append(self._connect_speaker_step())

        if self._ensure_serve_on_startup:
            steps.append(self._ensure_serve_step())

        return success(initialized=True, steps=steps)

    def _ensure_serve_step(self) -> dict[str, Any]:
        try:
            status = subprocess.run(
                ["systemctl", "is-active", "--quiet", "roamer-serve.service"],
                check=False,
                capture_output=True,
                text=True,
                timeout=self._serve_start_timeout_sec,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "name": "serve_init",
                "ok": False,
                "skipped": True,
                "reason": "systemd_unavailable",
                "message": str(exc),
            }

        if status.returncode == 0:
            return {
                "name": "serve_init",
                "ok": True,
                "service": "roamer-serve.service",
                "already_active": True,
            }

        try:
            start = subprocess.run(
                ["systemctl", "start", "roamer-serve.service"],
                check=False,
                capture_output=True,
                text=True,
                timeout=self._serve_start_timeout_sec,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "name": "serve_init",
                "ok": False,
                "service": "roamer-serve.service",
                "error": "serve_start_failed",
                "message": str(exc),
            }

        return {
            "name": "serve_init",
            "ok": start.returncode == 0,
            "service": "roamer-serve.service",
            "already_active": False,
            "exit_code": start.returncode,
            "stdout": self._decode_process_text(start.stdout),
            "stderr": self._decode_process_text(start.stderr),
            "error": None if start.returncode == 0 else "serve_start_failed",
        }

    def _configure_proxy_step(self) -> dict[str, Any]:
        script = Path(self._proxy_init_script).expanduser()
        if not script.exists():
            return {
                "name": "proxy_init",
                "ok": False,
                "skipped": True,
                "reason": "proxy_init_script_not_found",
                "script": str(script),
            }

        try:
            result = subprocess.run(
                [str(script)],
                check=False,
                capture_output=True,
                text=True,
                timeout=self._proxy_init_timeout_sec,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "name": "proxy_init",
                "ok": False,
                "script": str(script),
                "error": "proxy_init_timeout",
                "message": f"Proxy init timed out after {self._proxy_init_timeout_sec}s",
                "stdout": self._decode_process_text(exc.stdout),
                "stderr": self._decode_process_text(exc.stderr),
            }
        except OSError as exc:
            return {
                "name": "proxy_init",
                "ok": False,
                "script": str(script),
                "error": "proxy_init_failed",
                "message": str(exc),
            }

        stdout = self._decode_process_text(result.stdout)
        stderr = self._decode_process_text(result.stderr)
        proxy = stdout.strip().splitlines()[-1] if stdout.strip() else ""
        return {
            "name": "proxy_init",
            "ok": result.returncode == 0,
            "script": str(script),
            "proxy": proxy,
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "error": None if result.returncode == 0 else "proxy_init_failed",
        }

    @staticmethod
    def _decode_process_text(value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    def _connect_speaker_step(self) -> dict[str, Any]:
        if not self._speaker_mac:
            return {
                "name": "bluetooth_speaker_connect",
                "ok": False,
                "skipped": True,
                "reason": "speaker_mac_not_configured",
            }

        initial_status = self._bluetooth.status()
        if initial_status.get("ok"):
            for device in initial_status.get("connected_devices", []):
                if device.get("address") == self._speaker_mac:
                    return {
                        "name": "bluetooth_speaker_connect",
                        "ok": True,
                        "connected": True,
                        "address": self._speaker_mac,
                        "already_connected": True,
                        "waited_for_controller": False,
                        "connect_attempts": 0,
                    }

        controller_wait = self._wait_for_controller_ready(initial_status)
        if not controller_wait["ok"]:
            return {
                "name": "bluetooth_speaker_connect",
                "ok": False,
                "connected": False,
                "address": self._speaker_mac,
                "already_connected": False,
                "waited_for_controller": True,
                "controller_wait_seconds": controller_wait["waited_sec"],
                "error": "bluetooth_controller_not_ready",
                "message": controller_wait["message"],
                "error_code": ErrorCode.BLUETOOTH_CONTROLLER_UNAVAILABLE,
            }

        ready_status = controller_wait["status"]
        if ready_status.get("ok"):
            for device in ready_status.get("connected_devices", []):
                if device.get("address") == self._speaker_mac:
                    return {
                        "name": "bluetooth_speaker_connect",
                        "ok": True,
                        "connected": True,
                        "address": self._speaker_mac,
                        "already_connected": True,
                        "waited_for_controller": controller_wait["waited"],
                        "controller_wait_seconds": controller_wait["waited_sec"],
                        "connect_attempts": 0,
                    }

        connect_result = self._retry_connect_until_connected()
        return {
            "name": "bluetooth_speaker_connect",
            "ok": bool(connect_result.get("ok")),
            "connected": bool(connect_result.get("ok")),
            "address": self._speaker_mac,
            "already_connected": False,
            "waited_for_controller": controller_wait["waited"],
            "controller_wait_seconds": controller_wait["waited_sec"],
            "connect_attempts": connect_result.get("attempts", 0),
            "error": connect_result.get("error"),
            "message": connect_result.get("message"),
            "error_code": connect_result.get("error_code"),
        }

    def _wait_for_controller_ready(self, initial_status: dict[str, Any]) -> dict[str, Any]:
        start = time.monotonic()
        last_status = initial_status
        if last_status.get("ok"):
            return {
                "ok": True,
                "waited": False,
                "waited_sec": 0.0,
                "status": last_status,
            }

        while time.monotonic() - start < self._controller_ready_timeout_sec:
            time.sleep(self._retry_interval_sec)
            status = self._bluetooth.status()
            if status.get("ok"):
                return {
                    "ok": True,
                    "waited": True,
                    "waited_sec": round(time.monotonic() - start, 2),
                    "status": status,
                }
            last_status = status

        return {
            "ok": False,
            "waited": True,
            "waited_sec": round(time.monotonic() - start, 2),
            "message": last_status.get("message", "Bluetooth controller did not become ready"),
            "status": last_status,
        }

    def _retry_connect_until_connected(self) -> dict[str, Any]:
        start = time.monotonic()
        attempts = 0
        last_result: dict[str, Any] = {}

        while True:
            attempts += 1
            last_result = self._bluetooth.connect(self._speaker_mac)
            if last_result.get("ok"):
                return success(connected=True, address=self._speaker_mac, attempts=attempts)

            status = self._bluetooth.status()
            if status.get("ok"):
                for device in status.get("connected_devices", []):
                    if device.get("address") == self._speaker_mac:
                        return success(connected=True, address=self._speaker_mac, attempts=attempts)

            if time.monotonic() - start >= self._connect_retry_timeout_sec:
                break

            time.sleep(self._retry_interval_sec)

        return {
            "ok": False,
            "attempts": attempts,
            "error": last_result.get("error", "bluetooth_connect_failed"),
            "message": last_result.get(
                "message",
                "Bluetooth speaker connect retry budget exhausted",
            ),
            "error_code": last_result.get(
                "error_code",
                ErrorCode.BLUETOOTH_CONNECT_FAILED,
            ),
        }
