"""BlueZ Bluetooth driver using bluetoothctl."""

import re
import subprocess
from typing import Any

from roamer.drivers.bluetooth.base import BluetoothDriver
from roamer.drivers.registry import register_driver
from roamer.output import error, success


class BluezDriver(BluetoothDriver):
    """Bluetooth driver using bluetoothctl (BlueZ)."""

    def status(self) -> dict[str, Any]:
        """Get Bluetooth status.

        Returns:
            Result dict with controller and connected devices
        """
        controller = self._get_controller_info()
        if controller is None:
            return error("bluetooth_not_available", "No Bluetooth controller found")

        connected = self._get_connected_devices()

        return success(
            controller=controller,
            connected_devices=connected,
        )

    def connect(self, address: str) -> dict[str, Any]:
        """Connect to a Bluetooth device.

        Args:
            address: Device address (XX:XX:XX:XX:XX:XX)

        Returns:
            Result dict
        """
        # Try to connect
        try:
            result = subprocess.run(
                ["bluetoothctl", "connect", address],
                capture_output=True,
                timeout=30,
                input=b"",
            )
        except subprocess.TimeoutExpired:
            return error("bluetooth_connect_failed", "Connection timed out")
        except FileNotFoundError:
            return error("bluetooth_not_available", "bluetoothctl not installed")

        output = result.stdout.decode() + result.stderr.decode()

        if "Connection successful" in output or "connected: yes" in output.lower():
            return success(
                connected=True,
                address=address,
            )

        return error(
            "bluetooth_connect_failed",
            f"Failed to connect: {output.strip()}",
        )

    def disconnect(self, address: str) -> dict[str, Any]:
        """Disconnect from a Bluetooth device.

        Args:
            address: Device address

        Returns:
            Result dict
        """
        try:
            result = subprocess.run(
                ["bluetoothctl", "disconnect", address],
                capture_output=True,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            return error("bluetooth_error", "Disconnect timed out")
        except FileNotFoundError:
            return error("bluetooth_not_available", "bluetoothctl not installed")

        output = result.stdout.decode()

        if "Successful disconnected" in output or result.returncode == 0:
            return success(disconnected=True, address=address)

        return error("bluetooth_error", f"Failed to disconnect: {output.strip()}")

    def _get_controller_info(self) -> dict[str, Any] | None:
        """Get Bluetooth controller information.

        Returns:
            Controller info dict or None if not available
        """
        try:
            result = subprocess.run(
                ["bluetoothctl", "show"],
                capture_output=True,
                timeout=5,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

        if result.returncode != 0:
            return None

        output = result.stdout.decode()

        # Parse controller info
        info: dict[str, Any] = {}

        name_match = re.search(r"Name:\s*(.+)", output)
        if name_match:
            info["name"] = name_match.group(1).strip()

        addr_match = re.search(r"Controller\s+([0-9A-Fa-f:]+)", output)
        if addr_match:
            info["address"] = addr_match.group(1)

        info["powered"] = "Powered: yes" in output
        info["discoverable"] = "Discoverable: yes" in output

        return info if info else None

    def _get_connected_devices(self) -> list[dict[str, Any]]:
        """Get list of connected Bluetooth devices.

        Returns:
            List of connected device info dicts
        """
        try:
            result = subprocess.run(
                ["bluetoothctl", "devices", "Connected"],
                capture_output=True,
                timeout=5,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

        devices = []
        for line in result.stdout.decode().splitlines():
            # Format: Device XX:XX:XX:XX:XX:XX DeviceName
            match = re.match(r"Device\s+([0-9A-Fa-f:]+)\s+(.+)", line)
            if match:
                devices.append({
                    "address": match.group(1),
                    "name": match.group(2).strip(),
                })

        return devices


# Register this driver
register_driver("bluetooth", "bluez", BluezDriver)
