"""Interaction audio capability."""

import time
from collections.abc import Iterator
from datetime import datetime
from typing import Any

# Import drivers to register them
import roamer.plugins.interaction.drivers.audio  # noqa: F401
from roamer.platform.config import get_driver_config, get_driver_name
from roamer.platform.logging import log_event
from roamer.plugins.interaction.capabilities.base import Capability
from roamer.plugins.interaction.drivers.registry import get_driver


class AudioCapability(Capability):
    """Audio capability - record and play audio."""

    def __init__(self, config: dict[str, Any]):
        """Initialize audio capability.

        Args:
            config: Full configuration dictionary
        """
        super().__init__(config)
        driver_name = get_driver_name(config, "audio")
        driver_config = get_driver_config(config, driver_name)
        self._driver = get_driver("audio", driver_name, driver_config)

    def record(
        self,
        duration: float = 5.0,
        output: str | None = None,
    ) -> dict[str, Any]:
        """Record audio from microphone.

        Args:
            duration: Recording duration in seconds
            output: Output file path (auto-generated if None)

        Returns:
            Result dict with ok, path, duration_sec, sample_rate, channels
        """
        if output is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output = f"/tmp/roamer_rec_{timestamp}.wav"

        started_at = time.monotonic()
        log_event(
            "audio",
            "record_start",
            output=output,
            duration_sec=duration,
        )
        result = self._driver.record(output, duration)
        log_event(
            "audio",
            "record_done",
            output=output,
            duration_sec=duration,
            ok=bool(result.get("ok", False)),
            error_code=result.get("error_code"),
            duration_ms=_elapsed_ms(started_at),
        )
        return result

    def stream_chunks(
        self,
        *,
        chunk_duration_sec: float = 0.032,
        max_duration_sec: float = 10.0,
    ) -> Iterator[bytes]:
        """Stream raw audio chunks from the configured audio driver."""
        log_event(
            "audio",
            "stream_start",
            chunk_duration_sec=chunk_duration_sec,
            max_duration_sec=max_duration_sec,
        )
        iterator = self._driver.stream_chunks(
            chunk_duration_sec=chunk_duration_sec,
            max_duration_sec=max_duration_sec,
        )
        return self._logged_chunk_iterator(
            iterator,
            chunk_duration_sec=chunk_duration_sec,
            max_duration_sec=max_duration_sec,
        )

    def play(self, file: str) -> dict[str, Any]:
        """Play an audio file.

        Args:
            file: Audio file path

        Returns:
            Result dict with ok, played, duration_sec
        """
        started_at = time.monotonic()
        log_event("audio", "play_start", file=file)
        result = self._driver.play(file)
        log_event(
            "audio",
            "play_done",
            file=file,
            ok=bool(result.get("ok", False)),
            error_code=result.get("error_code"),
            duration_sec=result.get("duration_sec"),
            duration_ms=_elapsed_ms(started_at),
        )
        return result

    def _logged_chunk_iterator(
        self,
        iterator: Iterator[bytes],
        *,
        chunk_duration_sec: float,
        max_duration_sec: float | None,
    ) -> Iterator[bytes]:
        started_at = time.monotonic()
        chunk_count = 0
        try:
            for chunk in iterator:
                chunk_count += 1
                yield chunk
        except Exception as exc:
            log_event(
                "audio",
                "stream_error",
                chunk_duration_sec=chunk_duration_sec,
                max_duration_sec=max_duration_sec,
                chunk_count=chunk_count,
                exception_type=exc.__class__.__name__,
                message=str(exc),
                duration_ms=_elapsed_ms(started_at),
                level="ERROR",
            )
            raise
        finally:
            log_event(
                "audio",
                "stream_done",
                chunk_duration_sec=chunk_duration_sec,
                max_duration_sec=max_duration_sec,
                chunk_count=chunk_count,
                duration_ms=_elapsed_ms(started_at),
            )


def _elapsed_ms(started_at: float) -> float:
    return round((time.monotonic() - started_at) * 1000, 3)
