"""Stable command and runtime error contract."""

from __future__ import annotations

from enum import IntEnum, StrEnum

SCHEMA_VERSION = "1.0"
UNKNOWN_ERROR_CODE = "unknown_error"


class ExitCategory(IntEnum):
    SUCCESS = 0
    USAGE = 2
    DEPENDENCY = 10
    RUNTIME = 11
    TIMEOUT = 12


class ErrorCode(StrEnum):
    ACTION_NOT_FOUND = "action.not_found"
    CONFIG_INVALID = "config.invalid"
    DRIVER_NOT_FOUND = "driver.not_found"
    RESOURCE_BUSY = "resource.busy"
    CLIENT_TIMEOUT = "client.timeout"
    MODULE_UNAVAILABLE = "module.unavailable"
    POLICY_REJECTED = "policy.rejected"
    MOTION_UNAVAILABLE = "motion.unavailable"
    MOTION_POINT_UNKNOWN = "motion.point.unknown"
    MOTION_ROS2_UNAVAILABLE = "motion.ros2.unavailable"
    AUDIO_RECORD_FAILED = "audio.record.command_failed"
    AUDIO_PLAY_FAILED = "audio.play.command_failed"
    SPEECH_TTS_FAILED = "speech.tts.synthesis_failed"
    CAMERA_CAPTURE_FAILED = "camera.capture.failed"
    BLUETOOTH_RUNTIME_FAILED = "bluetooth.runtime.failed"
    COGNITION_UNAVAILABLE = "cognition.unavailable"
    CONTROL_PROTOCOL_ERROR = "control.protocol_error"


LEGACY_ERROR_MAP: dict[str, str] = {
    "action_not_found": ErrorCode.ACTION_NOT_FOUND.value,
    "config_invalid": ErrorCode.CONFIG_INVALID.value,
    "driver_not_found": ErrorCode.DRIVER_NOT_FOUND.value,
    "resource_busy": ErrorCode.RESOURCE_BUSY.value,
    "motion_point_unknown": ErrorCode.MOTION_POINT_UNKNOWN.value,
    "motion_position_unavailable": ErrorCode.MOTION_UNAVAILABLE.value,
    "audio_record_failed": ErrorCode.AUDIO_RECORD_FAILED.value,
    "audio_play_failed": ErrorCode.AUDIO_PLAY_FAILED.value,
    "tts_failed": ErrorCode.SPEECH_TTS_FAILED.value,
    "camera_capture_failed": ErrorCode.CAMERA_CAPTURE_FAILED.value,
    "bluetooth_error": ErrorCode.BLUETOOTH_RUNTIME_FAILED.value,
    "serve_request_failed": ErrorCode.CONTROL_PROTOCOL_ERROR.value,
    "serve_timeout": ErrorCode.CLIENT_TIMEOUT.value,
}

ERROR_EXIT_CATEGORY: dict[str, ExitCategory] = {
    UNKNOWN_ERROR_CODE: ExitCategory.RUNTIME,
    ErrorCode.ACTION_NOT_FOUND.value: ExitCategory.USAGE,
    ErrorCode.CONFIG_INVALID.value: ExitCategory.USAGE,
    ErrorCode.DRIVER_NOT_FOUND.value: ExitCategory.USAGE,
    ErrorCode.RESOURCE_BUSY.value: ExitCategory.RUNTIME,
    ErrorCode.CLIENT_TIMEOUT.value: ExitCategory.TIMEOUT,
    ErrorCode.MODULE_UNAVAILABLE.value: ExitCategory.RUNTIME,
    ErrorCode.POLICY_REJECTED.value: ExitCategory.USAGE,
    ErrorCode.MOTION_POINT_UNKNOWN.value: ExitCategory.USAGE,
    ErrorCode.CONTROL_PROTOCOL_ERROR.value: ExitCategory.USAGE,
}


def canonical_error_code(code: str | None) -> str:
    if not code:
        return UNKNOWN_ERROR_CODE
    return LEGACY_ERROR_MAP.get(code, code)


def exit_category_for_error(error_code: str | None) -> ExitCategory:
    return ERROR_EXIT_CATEGORY.get(canonical_error_code(error_code), ExitCategory.RUNTIME)
