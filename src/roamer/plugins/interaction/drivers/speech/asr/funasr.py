"""FunASR speech recognition driver."""

import contextlib
import sys
from pathlib import Path
from typing import Any

from roamer.platform.contract import ErrorCode
from roamer.platform.output import error, success
from roamer.plugins.interaction.drivers.registry import register_driver
from roamer.plugins.interaction.drivers.speech.asr.base import ASRDriver


class FunASRDriver(ASRDriver):
    """ASR driver using FunASR."""

    def __init__(self, config: dict[str, Any]):
        """Initialize FunASR driver.

        Args:
            config: Driver-specific configuration
        """
        super().__init__(config)
        self._model = None

    def _load_model(self) -> bool:
        """Load the FunASR model if not already loaded.

        Returns:
            True if model loaded successfully
        """
        if self._model is not None:
            return True

        try:
            from funasr import AutoModel
        except ImportError:
            return False

        model_name = self.config.get("model", "paraformer-zh-streaming")

        try:
            with contextlib.redirect_stdout(sys.stderr):
                self._model = AutoModel(model=model_name)
            return True
        except Exception:
            return False

    def transcribe(self, audio_path: str) -> dict[str, Any]:
        """Transcribe speech from audio file.

        Args:
            audio_path: Path to audio file

        Returns:
            Result dict with text, confidence
        """
        if not Path(audio_path).exists():
            return error(
                "asr_failed",
                f"Audio file not found: {audio_path}",
                error_code=ErrorCode.SPEECH_ASR_AUDIO_NOT_FOUND,
            )

        if not self._load_model():
            return error(
                "asr_failed",
                "Failed to load ASR model",
                error_code=ErrorCode.SPEECH_ASR_MODEL_LOAD_FAILED,
            )

        try:
            with contextlib.redirect_stdout(sys.stderr):
                result = self._model.generate(input=audio_path)
        except Exception as e:
            return error("asr_failed", str(e), error_code=ErrorCode.SPEECH_ASR_RUNTIME_FAILED)

        if not result:
            return error(
                "asr_failed",
                "No transcription result",
                error_code=ErrorCode.SPEECH_ASR_EMPTY_RESULT,
            )

        # FunASR returns list of results
        if isinstance(result, list) and len(result) > 0:
            item = result[0]
            text = item.get("text", "")
            # FunASR may not always return confidence
            confidence = item.get("confidence", None)
        else:
            text = str(result)
            confidence = None

        if not text:
            return success(
                text="",
                confidence=0.0,
            )

        return success(
            text=text,
            confidence=confidence,
        )


# Register this driver
register_driver("asr", "funasr", FunASRDriver)
