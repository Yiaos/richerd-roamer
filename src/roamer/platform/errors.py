"""Custom exceptions for Roamer."""

from roamer.platform.contract import ErrorCode


class RoamerError(Exception):
    """Base exception for Roamer errors."""

    code: str = "unknown_error"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class DriverNotFoundError(RoamerError):
    """Driver not found."""

    code = ErrorCode.DRIVER_NOT_FOUND.value
