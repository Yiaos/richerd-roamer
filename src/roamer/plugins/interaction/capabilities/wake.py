"""SU-03T GPIO-triggered hands-free wake loop."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from roamer.platform.contract import ErrorCode
from roamer.platform.logging import log_event, request_context
from roamer.platform.output import error, success
from roamer.platform.runtime import run_action
from roamer.plugins.interaction.capabilities.base import Capability
from roamer.plugins.interaction.capabilities.converse import ConverseCapability
from roamer.plugins.interaction.capabilities.listen import ListenCapability
from roamer.plugins.interaction.drivers.registry import get_driver
from roamer.plugins.interaction.services.endpointing import (
    ChunkVadAdapter,
    EndpointConfig,
    EndpointRecorder,
)
from roamer.plugins.interaction.services.preroll_audio import PreRollAudioSource
from roamer.plugins.interaction.services.wake_phrases import match_wake_phrase


class WakeCapability(Capability):
    """Hands-free wake loop driven by SU-03T GPIO and ASR confirmation."""

    def __init__(self, config: dict[str, Any], *, clock: Callable[[], float] | None = None):
        super().__init__(config)
        self._followup_until = 0.0
        self._last_trigger_at: float | None = None
        self._turn_id = 0
        self._clock = clock or time.monotonic

    def run(
        self,
        *,
        once: bool = False,
        timeout: float | None = None,
        no_sound: bool = False,
    ) -> dict[str, Any]:
        session_id = uuid.uuid4().hex[:12]
        deadline = self._clock() + float(timeout) if timeout is not None else None
        pre_roll_source = None

        try:
            try:
                pre_roll_source = self._start_preroll_source_if_needed()
            except FileNotFoundError:
                return error(
                    "audio_record_failed",
                    "Wake audio unavailable: arecord not installed",
                    error_code=ErrorCode.DEPENDENCY_AUDIO_ARECORD_MISSING,
                )
            except Exception as exc:
                return error(
                    "audio_record_failed",
                    f"Wake audio unavailable: {exc}",
                    error_code=ErrorCode.AUDIO_RECORD_COMMAND_FAILED,
                )

            while True:
                wait_timeout = self._remaining_timeout(deadline)
                if wait_timeout is not None and wait_timeout <= 0:
                    return success(completed=True, timeout=True, turns=[])

                try:
                    pre_roll_source = self._ensure_preroll_source(pre_roll_source)
                except FileNotFoundError:
                    return error(
                        "audio_record_failed",
                        "Wake audio unavailable: arecord not installed",
                        error_code=ErrorCode.DEPENDENCY_AUDIO_ARECORD_MISSING,
                    )
                except Exception as exc:
                    return error(
                        "audio_record_failed",
                        f"Wake audio unavailable: {exc}",
                        error_code=ErrorCode.AUDIO_RECORD_COMMAND_FAILED,
                    )

                if not self._in_followup():
                    try:
                        triggered = self._wait_for_trigger(wait_timeout)
                    except Exception as exc:
                        return error(
                            "converse_wakeword_unavailable",
                            f"Wake trigger unavailable: {exc}",
                            error_code=ErrorCode.CONVERSE_WAKEWORD_UNAVAILABLE,
                        )
                    if triggered and not self._accept_trigger():
                        continue
                    if not triggered:
                        if deadline is not None:
                            return success(completed=True, reason="wake_timeout", turns=[])
                        continue

                with request_context(uuid.uuid4().hex[:12]):
                    record_timeout = None if pre_roll_source is not None else wait_timeout
                    listen_result = self._listen_once(
                        timeout=record_timeout,
                        pre_roll_source=pre_roll_source,
                    )
                    if not listen_result.get("ok"):
                        if once:
                            return success(
                                completed=True,
                                turns=[{"stage": "listen", "ok": False, **listen_result}],
                                listen=listen_result,
                            )
                        continue

                    text = str(listen_result.get("text") or "").strip()
                    if not text:
                        continue
                    wake_cfg = self.config.get("converse", {}).get("wakeword", {})
                    logging_cfg = self.config.get("logging", {})
                    phrases = list(wake_cfg.get("phrases") or ["richard", "rich erd", "瑞彻德"])
                    match = match_wake_phrase(text, phrases)
                    in_followup = self._in_followup()
                    log_transcripts = bool(logging_cfg.get("log_transcripts", True))
                    command_text_log = (
                        match.command_text if match.matched and log_transcripts else ""
                    )
                    log_event(
                        "wake",
                        "asr_transcript",
                        text=text if log_transcripts else "",
                        matched=bool(match.matched),
                        phrase=match.phrase,
                        command_text=command_text_log,
                        in_followup=in_followup,
                    )
                    if not match.matched and not in_followup:
                        continue

                    command_text = match.command_text if match.matched else text
                    if match.matched and self._is_wake_phrase_only(command_text, phrases):
                        self._enter_followup()
                        continue
                    if not command_text:
                        self._enter_followup()
                        continue

                    self._turn_id += 1
                    turn = self._route_text(
                        text=command_text,
                        session_id=session_id,
                        turn_id=self._turn_id,
                        no_sound=no_sound,
                        allow_fallback=bool(match.matched),
                    )
                    if not turn.get("ok", True):
                        intent_result = turn.get("intent_result")
                        if isinstance(intent_result, dict):
                            return dict(intent_result)
                        return dict(turn)
                    if pre_roll_source is not None:
                        pre_roll_source.clear()
                    if turn.get("route") != "ignored":
                        self._enter_followup()
                    if once:
                        return success(completed=True, turns=[turn], wake_match=match.matched)
        finally:
            if pre_roll_source is not None:
                pre_roll_source.stop()

    def _remaining_timeout(self, deadline: float | None) -> float | None:
        if deadline is None:
            return None
        return max(0.0, deadline - self._clock())

    def _in_followup(self) -> bool:
        return self._clock() < self._followup_until

    def _enter_followup(self) -> None:
        wake_cfg = self.config.get("converse", {}).get("wakeword", {})
        timeout = float(wake_cfg.get("followup_timeout_sec", 10.0))
        self._followup_until = self._clock() + timeout

    def _accept_trigger(self) -> bool:
        wake_cfg = self.config.get("converse", {}).get("wakeword", {})
        min_interval = float(wake_cfg.get("min_interval_sec", 1.5))
        now = self._clock()
        if self._last_trigger_at is not None and now - self._last_trigger_at < min_interval:
            return False
        self._last_trigger_at = now
        return True

    def _is_wake_phrase_only(self, text: str, phrases: list[str]) -> bool:
        remaining = str(text or "").strip()
        if not remaining:
            return True

        matched = False
        while remaining:
            wake_match = match_wake_phrase(remaining, phrases)
            if not wake_match.matched:
                return False
            matched = True
            next_remaining = wake_match.command_text.strip()
            if next_remaining == remaining:
                return False
            remaining = next_remaining
        return matched

    def _wait_for_trigger(self, timeout: float | None) -> bool:
        wake_cfg = self.config.get("converse", {}).get("wakeword", {})
        driver_name = str(wake_cfg.get("driver") or "su03t_gpio")
        driver = get_driver("wakeword", driver_name, wake_cfg)
        driver.start()
        try:
            return bool(driver.wait_hit(timeout=float(timeout if timeout is not None else 1.0)))
        finally:
            driver.stop()

    def _ensure_preroll_source(
        self, pre_roll_source: PreRollAudioSource | None
    ) -> PreRollAudioSource | None:
        if pre_roll_source is None:
            return None
        if bool(getattr(pre_roll_source, "healthy", False)):
            return pre_roll_source

        reader_error = getattr(pre_roll_source, "reader_error", None)
        try:
            pre_roll_source.stop()
        finally:
            log_event(
                "wake",
                "preroll_restart",
                reason="reader_unhealthy",
                reader_error=str(reader_error) if reader_error else None,
            )
        return self._start_preroll_source_if_needed()

    def _listen_once(
        self,
        timeout: float | None,
        pre_roll_source: PreRollAudioSource | None = None,
    ) -> dict[str, Any]:
        if pre_roll_source is not None:
            return self._listen_once_with_preroll(timeout=timeout, pre_roll_source=pre_roll_source)

        endpoint = self.config.get("converse", {}).get("endpoint", {})
        max_record = float(endpoint.get("max_record_sec", timeout or 8.0))
        if timeout is not None:
            max_record = min(max_record, float(timeout))
        return run_action(
            "listen",
            timeout=max_record,
            save_audio=None,
            debug=False,
            use_endpointing=True,
        )

    def _listen_once_with_preroll(
        self,
        *,
        timeout: float | None,
        pre_roll_source: PreRollAudioSource,
    ) -> dict[str, Any]:
        listener = ListenCapability(self.config)
        endpoint_config = EndpointConfig.from_config(self.config, timeout=timeout)
        audio_path = listener._create_temp_audio("roamer_wake_")
        try:
            recorder = EndpointRecorder(
                chunk_source=pre_roll_source.capture_iter(
                    max_duration_sec=endpoint_config.max_record_sec
                ),
                vad_probability=ChunkVadAdapter(
                    listener._vad,
                    threshold=endpoint_config.threshold,
                ).probability,
                config=endpoint_config,
                output_path=audio_path,
            )
            record_result = recorder.record()
            if not record_result.get("ok"):
                return record_result
            return listener.transcribe_audio_file(
                audio_path,
                save_audio=None,
                debug=False,
                endpoint_metrics=record_result.get("endpoint_metrics"),
            )
        finally:
            try:
                Path(audio_path).unlink(missing_ok=True)
            except Exception:
                pass

    def _start_preroll_source_if_needed(self) -> PreRollAudioSource | None:
        if getattr(self._listen_once, "__func__", None) is not WakeCapability._listen_once:
            return None

        listener = ListenCapability(self.config)
        endpoint_config = EndpointConfig.from_config(self.config)
        wake_cfg = self.config.get("converse", {}).get("wakeword", {})
        pre_roll_sec = float(wake_cfg.get("pre_roll_sec", 0.8))
        source = PreRollAudioSource(
            chunk_source=listener._audio.stream_chunks(
                chunk_duration_sec=endpoint_config.chunk_duration_sec,
                max_duration_sec=None,
            ),
            chunk_duration_sec=endpoint_config.chunk_duration_sec,
            pre_roll_sec=pre_roll_sec,
        )
        source.start()
        return source

    def _route_text(
        self,
        *,
        text: str,
        session_id: str,
        turn_id: int,
        no_sound: bool,
        allow_fallback: bool,
    ) -> dict[str, Any]:
        return ConverseCapability(self.config).route_text(
            text,
            session_id=session_id,
            turn_id=turn_id,
            no_sound=no_sound,
            allow_fallback=allow_fallback,
        )
