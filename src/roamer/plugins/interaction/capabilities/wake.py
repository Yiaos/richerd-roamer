"""SU-03T GPIO-triggered hands-free wake loop."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from typing import Any

from roamer.platform.contract import ErrorCode
from roamer.platform.logging import current_request_id, log_event, request_context
from roamer.platform.output import error, success
from roamer.platform.runtime import run_action
from roamer.plugins.interaction.capabilities.base import Capability
from roamer.plugins.interaction.capabilities.converse import ConverseCapability
from roamer.plugins.interaction.capabilities.listen import ListenCapability
from roamer.plugins.interaction.drivers.registry import get_driver
from roamer.plugins.interaction.drivers.speech.stt.vllm_realtime import VllmRealtimeSTTProvider
from roamer.plugins.interaction.services.endpointing import (
    ChunkVadAdapter,
    EndpointConfig,
    EndpointRecorder,
)
from roamer.plugins.interaction.services.intent import match_intent
from roamer.plugins.interaction.services.playback_state import PlaybackState
from roamer.plugins.interaction.services.preroll_audio import PreRollAudioSource
from roamer.plugins.interaction.services.realtime_listen import RealtimeEndpointTranscriber
from roamer.plugins.interaction.services.wake_phrases import match_wake_phrase


class WakeCapability(Capability):
    """Hands-free wake loop driven by SU-03T GPIO and ASR confirmation."""

    def __init__(self, config: dict[str, Any], *, clock: Callable[[], float] | None = None):
        super().__init__(config)
        self._followup_until = 0.0
        self._last_trigger_at: float | None = None
        self._turn_id = 0
        self._clock = clock or time.monotonic
        self._playback_state = PlaybackState.from_config(config)
        self._armed_followup_after_playback: dict[str, Any] | None = None
        self._followup_turns = 0

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
                self._expire_followup_if_needed(session_id=session_id)
                wait_timeout = self._remaining_timeout(deadline)
                if (
                    wait_timeout is not None
                    and wait_timeout <= 0
                    and not self._in_followup()
                    and self._armed_followup_after_playback is None
                ):
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

                context = (
                    nullcontext()
                    if current_request_id() is not None
                    else request_context(uuid.uuid4().hex[:12])
                )
                with context:
                    if self._playback_state.is_active():
                        log_event(
                            "wake",
                            "listen_skipped_while_speaking",
                            session_id=session_id,
                            playback_generation=self._playback_state.generation(),
                        )
                        if once:
                            return success(
                                completed=True,
                                reason="speaking",
                                session_id=session_id,
                                turns=[],
                            )
                        time.sleep(0.1)
                        continue

                    self._enter_followup_if_armed_playback_done()
                    in_followup_wait = self._in_followup()
                    if not in_followup_wait:
                        wait_started_at = self._clock()
                        log_event(
                            "wake",
                            "trigger_wait_start",
                            session_id=session_id,
                            timeout_sec=wait_timeout,
                        )
                        trigger_wait_timeout = wait_timeout
                        if self._armed_followup_after_playback is not None:
                            trigger_wait_timeout = (
                                0.2
                                if wait_timeout is None
                                else min(float(wait_timeout), 0.2)
                            )
                        try:
                            triggered = self._wait_for_trigger(trigger_wait_timeout)
                        except Exception as exc:
                            return error(
                                "converse_wakeword_unavailable",
                                f"Wake trigger unavailable: {exc}",
                                error_code=ErrorCode.CONVERSE_WAKEWORD_UNAVAILABLE,
                            )
                        if triggered:
                            accepted = self._accept_trigger()
                            log_event(
                                "wake",
                                "trigger_hit",
                                session_id=session_id,
                                accepted=accepted,
                                duration_ms=round((self._clock() - wait_started_at) * 1000, 3),
                            )
                            if not accepted:
                                log_event(
                                    "wake",
                                    "trigger_rejected",
                                    session_id=session_id,
                                    reason="min_interval",
                                )
                                continue
                            self._disarm_followup_after_playback(
                                reason="gpio_triggered",
                                session_id=session_id,
                            )
                        else:
                            log_event(
                                "wake",
                                "trigger_timeout",
                                session_id=session_id,
                                timeout_sec=wait_timeout,
                                duration_ms=round((self._clock() - wait_started_at) * 1000, 3),
                            )
                            if deadline is not None:
                                return success(completed=True, reason="wake_timeout", turns=[])
                            continue

                    followup_remaining = self._followup_remaining()
                    if in_followup_wait:
                        record_timeout = followup_remaining
                    else:
                        record_timeout = None if pre_roll_source is not None else wait_timeout
                    listen_started_at = self._clock()
                    log_event(
                        "wake",
                        "listen_start",
                        level="DEBUG",
                        session_id=session_id,
                        timeout_sec=record_timeout,
                        in_followup=in_followup_wait,
                    )
                    listen_result = self._listen_once(
                        timeout=record_timeout,
                        pre_roll_source=pre_roll_source,
                    )
                    log_event(
                        "wake",
                        "listen_done",
                        level="DEBUG" if bool(listen_result.get("ok", False)) else "INFO",
                        session_id=session_id,
                        ok=bool(listen_result.get("ok", False)),
                        error_code=listen_result.get("error_code"),
                        duration_ms=round((self._clock() - listen_started_at) * 1000, 3),
                        endpoint_metrics=listen_result.get("endpoint_metrics"),
                    )
                    if not listen_result.get("ok"):
                        if (
                            in_followup_wait
                            and listen_result.get("error_code") == "speech.vad.no_speech"
                        ):
                            self._exit_followup(
                                reason="speech.vad.no_speech",
                                session_id=session_id,
                            )
                            if once:
                                return success(
                                    completed=True,
                                    reason="speech.vad.no_speech",
                                    session_id=session_id,
                                    turns=[],
                                    listen=listen_result,
                                )
                        if once:
                            return success(
                                completed=True,
                                turns=[{"stage": "listen", "ok": False, **listen_result}],
                                listen=listen_result,
                            )
                        continue

                    wake_cfg = self.config.get("converse", {}).get("wakeword", {})
                    logging_cfg = self.config.get("logging", {})
                    phrases = list(
                        wake_cfg.get("phrases") or ["richard", "rich erd", "瑞彻德", "理查德"]
                    )
                    log_transcripts = bool(logging_cfg.get("log_transcripts", True))
                    text = str(listen_result.get("text") or "").strip()
                    if not text:
                        log_event(
                            "wake",
                            "route_ignored",
                            session_id=session_id,
                            reason="empty_transcript",
                            text="",
                            matched=False,
                            in_followup=self._in_followup(),
                        )
                        if in_followup_wait:
                            self._exit_followup(reason="empty_transcript", session_id=session_id)
                            if once:
                                return success(
                                    completed=True,
                                    reason="empty_transcript",
                                    session_id=session_id,
                                    turns=[],
                                )
                        continue
                    match = match_wake_phrase(text, phrases)
                    in_followup = self._in_followup()
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
                        intent_result = match_intent(
                            text,
                            self.config.get("converse", {}).get("intents", []),
                        )
                        if not bool(intent_result.get("matched", False)):
                            log_event(
                                "wake",
                                "route_ignored",
                                session_id=session_id,
                                reason="wake_phrase_not_matched",
                                text=text if log_transcripts else "",
                                matched=False,
                                in_followup=in_followup,
                            )
                            continue

                    command_text = match.command_text if match.matched else text
                    if match.matched and self._is_wake_phrase_only(command_text, phrases):
                        self._enter_followup(
                            reason="wake_phrase_only",
                            session_id=session_id,
                            turn_id=None,
                        )
                        continue
                    if not command_text:
                        log_event(
                            "wake",
                            "route_ignored",
                            session_id=session_id,
                            reason="empty_command",
                            text="",
                            matched=bool(match.matched),
                            phrase=match.phrase,
                            in_followup=in_followup,
                        )
                        self._enter_followup(
                            reason="empty_command",
                            session_id=session_id,
                            turn_id=None,
                        )
                        continue
                    if self._is_stop_phrase(command_text):
                        self._exit_followup(reason="stop_phrase", session_id=session_id)
                        if once:
                            return success(
                                completed=True,
                                reason="stop_phrase",
                                session_id=session_id,
                                turns=[],
                            )
                        continue
                    if self._is_too_short_asr_text(command_text):
                        log_event(
                            "wake",
                            "route_ignored",
                            session_id=session_id,
                            reason="single_character_asr",
                            text=command_text if log_transcripts else "",
                            matched=bool(match.matched),
                            in_followup=in_followup,
                        )
                        if match.matched or in_followup:
                            self._exit_followup(
                                reason="single_character_asr",
                                session_id=session_id,
                            )
                            if once:
                                return success(
                                    completed=True,
                                    reason="single_character_asr",
                                    session_id=session_id,
                                    turns=[],
                                )
                        continue

                    self._turn_id += 1
                    route_started_at = self._clock()
                    log_event(
                        "wake",
                        "route_start",
                        session_id=session_id,
                        turn_id=self._turn_id,
                        text=command_text if log_transcripts else "",
                        matched=bool(match.matched),
                        in_followup=in_followup,
                    )
                    turn = self._route_text(
                        text=command_text,
                        session_id=session_id,
                        turn_id=self._turn_id,
                        no_sound=no_sound,
                        allow_fallback=bool(match.matched or in_followup),
                    )
                    log_event(
                        "wake",
                        "route_done",
                        session_id=session_id,
                        turn_id=self._turn_id,
                        ok=bool(turn.get("ok", True)),
                        error_code=turn.get("error_code"),
                        route=turn.get("route"),
                        action=turn.get("action"),
                        duration_ms=round((self._clock() - route_started_at) * 1000, 3),
                    )
                    if not turn.get("ok", True):
                        intent_result = turn.get("intent_result")
                        if isinstance(intent_result, dict):
                            return dict(intent_result)
                        return dict(turn)
                    if pre_roll_source is not None:
                        pre_roll_source.clear()
                    if turn.get("route") == "discord":
                        self._arm_followup_after_playback(
                            session_id=session_id,
                            turn_id=int(turn.get("turn_id") or self._turn_id),
                        )
                    elif turn.get("route") != "ignored":
                        self._followup_turns += 1
                        if self._followup_turns >= self._max_followup_turns():
                            self._exit_followup(
                                reason="max_followup_turns",
                                session_id=session_id,
                                turn_id=self._turn_id,
                            )
                        else:
                            self._enter_followup(
                                reason="route_done",
                                session_id=session_id,
                                turn_id=self._turn_id,
                            )
                    elif in_followup:
                        self._exit_followup(
                            reason="route_ignored",
                            session_id=session_id,
                            turn_id=self._turn_id,
                        )
                    if once:
                        return success(
                            completed=True,
                            session_id=session_id,
                            turns=[turn],
                            wake_match=match.matched,
                        )
        finally:
            if pre_roll_source is not None:
                pre_roll_source.stop()

    def _remaining_timeout(self, deadline: float | None) -> float | None:
        if deadline is None:
            return None
        return max(0.0, deadline - self._clock())

    def _in_followup(self) -> bool:
        return self._clock() < self._followup_until

    def _followup_remaining(self) -> float:
        return max(0.0, self._followup_until - self._clock())

    def _enter_followup(
        self,
        *,
        reason: str,
        session_id: str | None = None,
        turn_id: int | None = None,
    ) -> None:
        wake_cfg = self.config.get("converse", {}).get("wakeword", {})
        if not bool(wake_cfg.get("continuous_followup_enabled", True)):
            return
        timeout = float(wake_cfg.get("followup_timeout_sec", 3.0))
        was_active = self._in_followup()
        self._followup_until = self._clock() + timeout
        log_event(
            "wake",
            "followup_refresh" if was_active else "followup_start",
            session_id=session_id,
            turn_id=turn_id,
            reason=reason,
            timeout_sec=timeout,
            remaining_sec=timeout,
            followup_until=self._followup_until,
        )

    def _exit_followup(
        self,
        *,
        reason: str,
        session_id: str | None = None,
        turn_id: int | None = None,
    ) -> None:
        was_active = self._in_followup()
        self._followup_until = 0.0
        self._followup_turns = 0
        log_event(
            "wake",
            "followup_exit",
            session_id=session_id,
            turn_id=turn_id,
            reason=reason,
            was_active=was_active,
            remaining_sec=0.0,
        )

    def _expire_followup_if_needed(self, *, session_id: str | None = None) -> None:
        if self._followup_until <= 0.0 or self._in_followup():
            return
        self._exit_followup(reason="followup_timeout", session_id=session_id)

    def _max_followup_turns(self) -> int:
        wake_cfg = self.config.get("converse", {}).get("wakeword", {})
        return max(1, int(wake_cfg.get("max_followup_turns", 3)))

    def _arm_followup_after_playback(self, *, session_id: str, turn_id: int) -> None:
        self._followup_until = 0.0
        self._armed_followup_after_playback = {
            "session_id": session_id,
            "turn_id": turn_id,
            "after_generation": self._playback_state.generation(),
        }
        log_event(
            "wake",
            "followup_armed_after_playback",
            session_id=session_id,
            turn_id=turn_id,
            after_generation=self._armed_followup_after_playback["after_generation"],
            armed_after_generation=self._armed_followup_after_playback["after_generation"],
        )

    def _disarm_followup_after_playback(
        self,
        *,
        reason: str,
        session_id: str | None = None,
    ) -> None:
        if self._armed_followup_after_playback is None:
            return
        armed = self._armed_followup_after_playback
        self._armed_followup_after_playback = None
        log_event(
            "wake",
            "followup_disarmed",
            session_id=session_id or armed.get("session_id"),
            turn_id=armed.get("turn_id"),
            reason=reason,
        )

    def _enter_followup_if_armed_playback_done(self) -> bool:
        armed = self._armed_followup_after_playback
        if armed is None:
            return False
        if self._playback_state.is_active():
            return False
        generation = self._playback_state.generation()
        if generation <= int(armed.get("after_generation") or 0):
            return False

        self._armed_followup_after_playback = None
        log_event(
            "wake",
            "playback_done_observed",
            session_id=armed.get("session_id"),
            turn_id=armed.get("turn_id"),
            playback_generation=generation,
        )
        self._enter_followup(
            reason="playback_done",
            session_id=str(armed.get("session_id") or ""),
            turn_id=int(armed.get("turn_id") or 0) or None,
        )
        return True

    def _is_too_short_asr_text(self, text: str) -> bool:
        meaningful_chars = [
            char for char in str(text or "") if char.isalnum() or "\u4e00" <= char <= "\u9fff"
        ]
        return len(meaningful_chars) <= 1

    def _is_stop_phrase(self, text: str) -> bool:
        wake_cfg = self.config.get("converse", {}).get("wakeword", {})
        phrases = [str(phrase) for phrase in wake_cfg.get("stop_phrases", [])]
        normalized = "".join(
            char for char in str(text or "") if char.isalnum() or "\u4e00" <= char <= "\u9fff"
        )
        return any(phrase and phrase in normalized for phrase in phrases)

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
            wait_timeout = None if timeout is None else float(timeout)
            return bool(driver.wait_hit(timeout=wait_timeout))
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
            realtime_result = self._listen_preroll_realtime_if_configured(
                listener=listener,
                endpoint_config=endpoint_config,
                audio_path=audio_path,
                pre_roll_source=pre_roll_source,
            )
            if realtime_result is not None:
                return realtime_result

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

    def _listen_preroll_realtime_if_configured(
        self,
        *,
        listener: ListenCapability,
        endpoint_config: EndpointConfig,
        audio_path: str,
        pre_roll_source: PreRollAudioSource,
    ) -> dict[str, Any] | None:
        stt_cfg = self.config.get("converse", {}).get("stt", {})
        mode = str(stt_cfg.get("mode") or "batch")
        if mode not in {"realtime", "realtime_with_batch_fallback"}:
            return None
        provider_name = str(stt_cfg.get("provider") or "vllm_realtime")
        if provider_name != "vllm_realtime":
            return None
        if "chunk_duration_sec" in stt_cfg:
            endpoint_config = replace(
                endpoint_config,
                chunk_duration_sec=max(
                    EndpointConfig.chunk_duration_sec,
                    float(stt_cfg["chunk_duration_sec"]),
                ),
            )

        fallback_enabled = (
            mode == "realtime_with_batch_fallback" or stt_cfg.get("fallback") == "batch"
        )

        def fallback_transcribe(
            path: str, endpoint_metrics: dict[str, Any] | None
        ) -> dict[str, Any]:
            return listener.transcribe_audio_file(
                path,
                save_audio=None,
                debug=False,
                endpoint_metrics=endpoint_metrics,
            )

        transcriber = RealtimeEndpointTranscriber(
            chunk_source=pre_roll_source.capture_iter(
                max_duration_sec=endpoint_config.max_record_sec
            ),
            vad_probability=ChunkVadAdapter(
                listener._vad,
                threshold=endpoint_config.threshold,
            ).probability,
            endpoint_config=endpoint_config,
            provider=VllmRealtimeSTTProvider({**stt_cfg, "provider": provider_name}),
            output_path=audio_path,
            response_timeout_sec=float(stt_cfg.get("response_timeout_sec", 20.0)),
            fallback_transcribe=fallback_transcribe if fallback_enabled else None,
        )
        return transcriber.transcribe()

    def _start_preroll_source_if_needed(self) -> PreRollAudioSource | None:
        if getattr(self._listen_once, "__func__", None) is not WakeCapability._listen_once:
            return None

        listener = ListenCapability(self.config)
        endpoint_config = EndpointConfig.from_config(self.config)
        wake_cfg = self.config.get("converse", {}).get("wakeword", {})
        pre_roll_sec = float(wake_cfg.get("pre_roll_sec", 1.0))
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
