"""Custom exceptions for Roamer."""


class RoamerError(Exception):
    """Base exception for Roamer errors."""

    code: str = "unknown_error"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class CameraNotFoundError(RoamerError):
    """Camera device not found."""

    code = "camera_not_found"


class CameraCaptureError(RoamerError):
    """Camera capture failed."""

    code = "camera_capture_failed"


class AudioDeviceNotFoundError(RoamerError):
    """Audio device not found."""

    code = "audio_device_not_found"


class AudioRecordError(RoamerError):
    """Audio recording failed."""

    code = "audio_record_failed"


class AudioPlayError(RoamerError):
    """Audio playback failed."""

    code = "audio_play_failed"


class TTSError(RoamerError):
    """Text-to-speech failed."""

    code = "tts_failed"


class ASRError(RoamerError):
    """Speech recognition failed."""

    code = "asr_failed"


class VADNoSpeechError(RoamerError):
    """No speech detected by VAD."""

    code = "vad_no_speech"


class BluetoothError(RoamerError):
    """Bluetooth operation failed."""

    code = "bluetooth_error"


class BluetoothNotAvailableError(RoamerError):
    """Bluetooth controller not available."""

    code = "bluetooth_not_available"


class BluetoothConnectError(RoamerError):
    """Bluetooth connection failed."""

    code = "bluetooth_connect_failed"


class ConfigError(RoamerError):
    """Configuration error."""

    code = "config_invalid"


class DriverNotFoundError(RoamerError):
    """Driver not found."""

    code = "driver_not_found"
