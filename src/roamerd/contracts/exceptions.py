"""Runtime exceptions."""

from __future__ import annotations


class RoamerdError(RuntimeError):
    """Base roamerd exception."""


class DriverNotFoundError(RoamerdError):
    """Raised when a configured driver is unavailable."""


class ResourceBusyError(RoamerdError):
    """Raised when an action tries to use an occupied resource."""
