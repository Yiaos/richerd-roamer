from __future__ import annotations

from enum import IntEnum

from roamerd.contracts.errors import UNKNOWN_ERROR_CODE, ErrorCode, canonical_error_code


class ExitCategory(IntEnum):
    SUCCESS = 0
    USAGE = 2
    DEPENDENCY = 10
    RUNTIME = 11
    TIMEOUT = 12


_TIMEOUT_ERRORS = {
    ErrorCode.AUDIO_RECORD_TIMEOUT.value,
    ErrorCode.AUDIO_PLAY_TIMEOUT.value,
    ErrorCode.AUDIO_CONVERT_TIMEOUT.value,
    ErrorCode.SPEECH_TTS_TIMEOUT.value,
    ErrorCode.BLUETOOTH_CONNECT_TIMEOUT.value,
    ErrorCode.BLUETOOTH_DISCONNECT_TIMEOUT.value,
    ErrorCode.MOTION_GOTO_TIMEOUT.value,
    ErrorCode.MOTION_HOME_TIMEOUT.value,
    ErrorCode.SERVE_TIMEOUT.value,
    ErrorCode.TIMEOUT.value,
}

_DEPENDENCY_ERRORS = {
    ErrorCode.DEPENDENCY_AUDIO_ARECORD_MISSING.value,
    ErrorCode.DEPENDENCY_AUDIO_APLAY_MISSING.value,
    ErrorCode.DEPENDENCY_AUDIO_FFMPEG_MISSING.value,
    ErrorCode.DEPENDENCY_TTS_EDGE_TTS_MISSING.value,
    ErrorCode.DEPENDENCY_TTS_PIPER_BINARY_MISSING.value,
    ErrorCode.DEPENDENCY_TTS_PIPER_BINARY_NOT_EXECUTABLE.value,
    ErrorCode.DEPENDENCY_TTS_PIPER_MODEL_MISSING.value,
    ErrorCode.DEPENDENCY_BLUETOOTH_BLUETOOTHCTL_MISSING.value,
}

_USAGE_ERRORS = {
    ErrorCode.CONFIG_INVALID.value,
    ErrorCode.MOTION_POINT_UNKNOWN.value,
    ErrorCode.MOTION_POINT_INVALID.value,
    ErrorCode.MOTION_GOTO_GUARD_FAILED.value,
    ErrorCode.DRIVER_NOT_FOUND.value,
    ErrorCode.ACTION_NOT_FOUND.value,
}


def exit_category_for_error(error_code: str | ErrorCode | None) -> ExitCategory:
    canonical = canonical_error_code(error_code)
    if canonical in _TIMEOUT_ERRORS:
        return ExitCategory.TIMEOUT
    if canonical in _DEPENDENCY_ERRORS:
        return ExitCategory.DEPENDENCY
    if canonical in _USAGE_ERRORS:
        return ExitCategory.USAGE
    if canonical == UNKNOWN_ERROR_CODE:
        return ExitCategory.RUNTIME
    return ExitCategory.RUNTIME
