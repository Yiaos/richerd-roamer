"""Driver registry for dynamic driver loading."""

from typing import Any

from roamer.platform.errors import DriverNotFoundError

# Registry: capability -> driver_name -> driver_class
_DRIVERS: dict[str, dict[str, type]] = {}


def register_driver(capability: str, name: str, cls: type) -> None:
    """Register a driver class.

    Args:
        capability: Capability name (camera, audio, tts, etc.)
        name: Driver name (fswebcam, alsa, piper, etc.)
        cls: Driver class
    """
    if capability not in _DRIVERS:
        _DRIVERS[capability] = {}
    _DRIVERS[capability][name] = cls


def get_driver(capability: str, name: str, config: dict[str, Any]) -> Any:
    """Get a driver instance.

    Args:
        capability: Capability name
        name: Driver name
        config: Driver configuration

    Returns:
        Driver instance

    Raises:
        DriverNotFoundError: If driver is not registered
    """
    if capability not in _DRIVERS or name not in _DRIVERS[capability]:
        raise DriverNotFoundError(f"Unknown driver: {capability}/{name}")
    return _DRIVERS[capability][name](config)


def list_drivers(capability: str | None = None) -> dict[str, list[str]]:
    """List registered drivers.

    Args:
        capability: Optional capability to filter by

    Returns:
        Dict mapping capability names to lists of driver names
    """
    if capability is not None:
        return {capability: list(_DRIVERS.get(capability, {}).keys())}
    return {cap: list(drivers.keys()) for cap, drivers in _DRIVERS.items()}
