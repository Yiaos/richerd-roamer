"""Roamer drivers."""

# Import all driver packages to register them
from roamer.drivers import (
    audio,  # noqa: F401
    bluetooth,  # noqa: F401
    camera,  # noqa: F401
    speech,  # noqa: F401
)
from roamer.drivers.registry import get_driver, list_drivers, register_driver

__all__ = [
    "get_driver",
    "list_drivers",
    "register_driver",
]
