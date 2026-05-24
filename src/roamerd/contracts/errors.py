from __future__ import annotations

from enum import StrEnum

SCHEMA_VERSION = "1.0"
UNKNOWN_ERROR_CODE = "unknown_error"


class ErrorCode(StrEnum):
    CAMERA_NOT_FOUND = "camera.not_found"
    CAMERA_CAPTURE_FAILED = "camera.capture.failed"
    AUDIO_DEVICE_NOT_FOUND = "audio.device.not_found"
    AUDIO_RECORD_TIMEOUT = "audio.record.timeout"
    AUDIO_RECORD_COMMAND_FAILED = "audio.record.command_failed"
    AUDIO_RECORD_OUTPUT_MISSING = "audio.record.output_missing"
    AUDIO_PLAY_TIMEOUT = "audio.play.timeout"
    AUDIO_PLAY_COMMAND_FAILED = "audio.play.command_failed"
    AUDIO_LOAD_FAILED = "audio.load.failed"
    AUDIO_SAVE_FAILED = "audio.save.failed"
    AUDIO_CONVERT_TIMEOUT = "audio.convert.timeout"
    AUDIO_CONVERT_FAILED = "audio.convert.failed"
    SPEECH_VAD_FAILED = "speech.vad.failed"
    SPEECH_VAD_NO_SPEECH = "speech.vad.no_speech"
    SPEECH_ASR_AUDIO_NOT_FOUND = "speech.asr.audio_not_found"
    SPEECH_ASR_MODEL_LOAD_FAILED = "speech.asr.model_load_failed"
    SPEECH_ASR_RUNTIME_FAILED = "speech.asr.runtime_failed"
    SPEECH_ASR_EMPTY_RESULT = "speech.asr.empty_result"
    SPEECH_TTS_TIMEOUT = "speech.tts.timeout"
    SPEECH_TTS_SYNTHESIS_FAILED = "speech.tts.synthesis_failed"
    SPEECH_TTS_OUTPUT_MISSING = "speech.tts.output_missing"
    BLUETOOTH_CONTROLLER_UNAVAILABLE = "bluetooth.controller.unavailable"
    BLUETOOTH_CONNECT_TIMEOUT = "bluetooth.connect.timeout"
    BLUETOOTH_CONNECT_FAILED = "bluetooth.connect.failed"
    BLUETOOTH_DISCONNECT_TIMEOUT = "bluetooth.disconnect.timeout"
    BLUETOOTH_DISCONNECT_FAILED = "bluetooth.disconnect.failed"
    BLUETOOTH_RUNTIME_FAILED = "bluetooth.runtime.failed"
    DEPENDENCY_AUDIO_ARECORD_MISSING = "dependency.audio.arecord_missing"
    DEPENDENCY_AUDIO_APLAY_MISSING = "dependency.audio.aplay_missing"
    DEPENDENCY_AUDIO_FFMPEG_MISSING = "dependency.audio.ffmpeg_missing"
    DEPENDENCY_TTS_EDGE_TTS_MISSING = "dependency.tts.edge_tts_missing"
    DEPENDENCY_TTS_PIPER_BINARY_MISSING = "dependency.tts.piper_binary_missing"
    DEPENDENCY_TTS_PIPER_BINARY_NOT_EXECUTABLE = (
        "dependency.tts.piper_binary_not_executable"
    )
    DEPENDENCY_TTS_PIPER_MODEL_MISSING = "dependency.tts.piper_model_missing"
    DEPENDENCY_BLUETOOTH_BLUETOOTHCTL_MISSING = (
        "dependency.bluetooth.bluetoothctl_missing"
    )
    MOTION_STATUS_UNSUPPORTED = "motion.status.unsupported"
    MOTION_POSITION_UNAVAILABLE = "motion.position.unavailable"
    MOTION_POINT_UNKNOWN = "motion.point.unknown"
    MOTION_POINT_INVALID = "motion.point.invalid"
    MOTION_GOTO_GUARD_FAILED = "motion.goto.guard_failed"
    MOTION_GOTO_TIMEOUT = "motion.goto.timeout"
    MOTION_HOME_TIMEOUT = "motion.home.timeout"
    CONVERSE_INTENT_INVALID_ACTION = "converse.intent.invalid_action"
    CONVERSE_DISCORD_SEND_FAILED = "converse.discord.send_failed"
    CONVERSE_WAKEWORD_UNAVAILABLE = "converse.wakeword.unavailable"
    CONVERSE_LISTEN_FAILED = "converse.listen.failed"
    SERVE_UNAVAILABLE = "serve.unavailable"
    SERVE_TIMEOUT = "serve.timeout"
    SERVE_REQUEST_FAILED = "serve.request_failed"
    CONFIG_INVALID = "config.invalid"
    DRIVER_NOT_FOUND = "driver.not_found"
    ACTION_NOT_FOUND = "action.not_found"
    BUSY = "busy"
    TIMEOUT = "timeout"


LEGACY_ERROR_MAP: dict[str, ErrorCode] = {
    "camera_not_found": ErrorCode.CAMERA_NOT_FOUND,
    "camera_capture_failed": ErrorCode.CAMERA_CAPTURE_FAILED,
    "audio_device_not_found": ErrorCode.AUDIO_DEVICE_NOT_FOUND,
    "audio_record_failed": ErrorCode.AUDIO_RECORD_COMMAND_FAILED,
    "audio_play_failed": ErrorCode.AUDIO_PLAY_COMMAND_FAILED,
    "audio_load_failed": ErrorCode.AUDIO_LOAD_FAILED,
    "audio_save_failed": ErrorCode.AUDIO_SAVE_FAILED,
    "vad_failed": ErrorCode.SPEECH_VAD_FAILED,
    "asr_failed": ErrorCode.SPEECH_ASR_RUNTIME_FAILED,
    "tts_failed": ErrorCode.SPEECH_TTS_SYNTHESIS_FAILED,
    "vad_no_speech": ErrorCode.SPEECH_VAD_NO_SPEECH,
    "bluetooth_connect_failed": ErrorCode.BLUETOOTH_CONNECT_FAILED,
    "bluetooth_not_available": ErrorCode.BLUETOOTH_CONTROLLER_UNAVAILABLE,
    "bluetooth_error": ErrorCode.BLUETOOTH_RUNTIME_FAILED,
    "config_invalid": ErrorCode.CONFIG_INVALID,
    "driver_not_found": ErrorCode.DRIVER_NOT_FOUND,
    "action_not_found": ErrorCode.ACTION_NOT_FOUND,
    "converse_discord_send_failed": ErrorCode.CONVERSE_DISCORD_SEND_FAILED,
    "converse_wakeword_unavailable": ErrorCode.CONVERSE_WAKEWORD_UNAVAILABLE,
    "converse_listen_failed": ErrorCode.CONVERSE_LISTEN_FAILED,
    "converse_intent_invalid_action": ErrorCode.CONVERSE_INTENT_INVALID_ACTION,
    "serve_unavailable": ErrorCode.SERVE_UNAVAILABLE,
    "serve_timeout": ErrorCode.SERVE_TIMEOUT,
    "serve_request_failed": ErrorCode.SERVE_REQUEST_FAILED,
}


def canonical_error_code(code: str | ErrorCode | None) -> str:
    if code is None or code == "":
        return UNKNOWN_ERROR_CODE
    if isinstance(code, ErrorCode):
        return code.value
    if code in LEGACY_ERROR_MAP:
        return LEGACY_ERROR_MAP[code].value
    return code
