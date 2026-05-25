import pytest

from roamerd.capabilities.speech.drivers.bluez import BluezBluetoothDriver, parse_connected


def test_parse_connected_from_bluetoothctl_info() -> None:
    assert parse_connected("Name: Speaker\nConnected: yes\n") is True
    assert parse_connected("Connected: no\n") is False


@pytest.mark.asyncio
async def test_bluez_driver_status_and_connect_commands() -> None:
    calls: list[list[str]] = []

    async def runner(command: list[str], timeout_sec: float) -> str:
        calls.append(command)
        if command[:2] == ["bluetoothctl", "info"]:
            return "Connected: no\n"
        return ""

    driver = BluezBluetoothDriver("AA:BB", command_runner=runner)

    assert await driver.status() == "disconnected"
    await driver.connect()
    await driver.disconnect()

    assert calls == [
        ["bluetoothctl", "info", "AA:BB"],
        ["bluetoothctl", "connect", "AA:BB"],
        ["bluetoothctl", "disconnect", "AA:BB"],
    ]
