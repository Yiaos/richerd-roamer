from __future__ import annotations

from roamerd.contracts.errors import ErrorCode


class RoamerdError(Exception):
    code: ErrorCode = ErrorCode.BUSY

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class DriverNotFoundError(RoamerdError):
    code = ErrorCode.DRIVER_NOT_FOUND


class ConfigError(RoamerdError):
    code = ErrorCode.CONFIG_INVALID


class ActionError(RoamerdError):
    code = ErrorCode.ACTION_NOT_FOUND
