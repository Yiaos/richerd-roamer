"""Tests for error contract utilities."""

from roamer.platform.contract import ERROR_EXIT_CATEGORY, LEGACY_ERROR_MAP, ErrorCode, ExitCategory


def test_error_code_values_are_unique():
    """Error code values should be globally unique."""
    values = [error_code.value for error_code in ErrorCode]
    assert len(values) == len(set(values))


def test_legacy_map_keys_present():
    """Legacy compatibility keys should stay available for callers."""
    expected_keys = {
        "audio_record_failed",
        "audio_play_failed",
        "asr_failed",
        "tts_failed",
        "vad_no_speech",
        "bluetooth_connect_failed",
        "bluetooth_not_available",
        "bluetooth_error",
    }
    assert expected_keys.issubset(set(LEGACY_ERROR_MAP))


def test_motion_namespace_codes_are_stable():
    """Motion namespace codes should remain backward compatible."""
    assert ErrorCode.MOTION_STATUS_UNSUPPORTED.value == "motion.status.unsupported"
    assert ErrorCode.MOTION_POSITION_UNAVAILABLE.value == "motion.position.unavailable"
    assert ErrorCode.MOTION_POINT_UNKNOWN.value == "motion.point.unknown"
    assert ErrorCode.MOTION_POINT_INVALID.value == "motion.point.invalid"
    assert ErrorCode.MOTION_GOTO_GUARD_FAILED.value == "motion.goto.guard_failed"
    assert ErrorCode.MOTION_GOTO_TIMEOUT.value == "motion.goto.timeout"
    assert ErrorCode.MOTION_HOME_TIMEOUT.value == "motion.home.timeout"


def test_timeout_codes_map_to_timeout_exit_category():
    """Timeout-classified canonical codes should map to timeout exit category."""
    timeout_codes = {
        ErrorCode.AUDIO_RECORD_TIMEOUT.value,
        ErrorCode.AUDIO_PLAY_TIMEOUT.value,
        ErrorCode.AUDIO_CONVERT_TIMEOUT.value,
        ErrorCode.SPEECH_TTS_TIMEOUT.value,
        ErrorCode.BLUETOOTH_CONNECT_TIMEOUT.value,
        ErrorCode.BLUETOOTH_DISCONNECT_TIMEOUT.value,
        ErrorCode.MOTION_GOTO_TIMEOUT.value,
        ErrorCode.MOTION_HOME_TIMEOUT.value,
    }
    for code in timeout_codes:
        assert ERROR_EXIT_CATEGORY[code] == ExitCategory.TIMEOUT


def test_dependency_codes_map_to_dependency_exit_category():
    """Dependency-classified canonical codes should map to dependency exit category."""
    dependency_codes = {
        ErrorCode.DEPENDENCY_AUDIO_ARECORD_MISSING.value,
        ErrorCode.DEPENDENCY_AUDIO_APLAY_MISSING.value,
        ErrorCode.DEPENDENCY_AUDIO_FFMPEG_MISSING.value,
        ErrorCode.DEPENDENCY_TTS_EDGE_TTS_MISSING.value,
        ErrorCode.DEPENDENCY_TTS_PIPER_BINARY_MISSING.value,
        ErrorCode.DEPENDENCY_TTS_PIPER_BINARY_NOT_EXECUTABLE.value,
        ErrorCode.DEPENDENCY_TTS_PIPER_MODEL_MISSING.value,
        ErrorCode.DEPENDENCY_BLUETOOTH_BLUETOOTHCTL_MISSING.value,
    }
    for code in dependency_codes:
        assert ERROR_EXIT_CATEGORY[code] == ExitCategory.DEPENDENCY


def test_speech_asr_runtime_failed_code_is_stable():
    """ASR runtime error code value should remain backward compatible."""
    assert ErrorCode.SPEECH_ASR_RUNTIME_FAILED.value == "speech.asr.runtime_failed"


def test_converse_namespace_codes_are_stable():
    """Converse namespace codes should remain backward compatible."""
    assert ErrorCode.CONVERSE_INTENT_INVALID_ACTION.value == "converse.intent.invalid_action"
    assert ErrorCode.CONVERSE_DISCORD_SEND_FAILED.value == "converse.discord.send_failed"
    assert ErrorCode.CONVERSE_WAKEWORD_UNAVAILABLE.value == "converse.wakeword.unavailable"
    assert ErrorCode.CONVERSE_LISTEN_FAILED.value == "converse.listen.failed"
