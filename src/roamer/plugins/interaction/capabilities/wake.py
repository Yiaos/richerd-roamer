"""SU-03T GPIO-triggered hands-free wake loop."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from roamer.platform.output import success
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

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._followup_until = 0.0
        self._turn_id = 0

    def run(
        self,
        *,
        once: bool = False,
        timeout: float | None = None,
        no_sound: bool = False,
    ) -> dict[str, Any]:
        session_id = uuid.uuid4().hex[:12]
        turns: list[dict[str, Any]] = []
        deadline = time.monotonic() + float(timeout) if timeout is not None else None
        pre_roll_source = self._start_preroll_source_if_needed()

        try:
            while True:
                wait_timeout = self._remaining_timeout(deadline)
                if wait_timeout is not None and wait_timeout <= 0:
                    return success(completed=True, timeout=True, turns=turns)

                if not self._in_followup():
                    if not self._wait_for_trigger(wait_timeout):
                        if deadline is not None:
                            return success(completed=True, reason="wake_timeout", turns=turns)
                        continue

                listen_result = self._listen_once(
                    timeout=wait_timeout,
                    pre_roll_source=pre_roll_source,
                )
                if not listen_result.get("ok"):
                    turns.append({"stage": "listen", "ok": False, **listen_result})
                    if once:
                        return success(completed=True, turns=turns, listen=listen_result)
                    continue

                text = str(listen_result.get("text") or "").strip()
                wake_cfg = self.config.get("converse", {}).get("wakeword", {})
                phrases = list(wake_cfg.get("phrases") or ["richard", "rich erd", "瑞彻德"])
                match = match_wake_phrase(text, phrases)
                in_followup = self._in_followup()
                if not match.matched and not in_followup:
                    result = success(
                        completed=True,
                        ignored=True,
                        reason="wake_phrase_not_matched",
                        text=text,
                        turns=turns,
                    )
                    if once:
                        return result
                    continue

                command_text = match.command_text if match.matched else text
                if not command_text:
                    self._enter_followup()
                    result = success(completed=True, followup=True, text=text, turns=turns)
                    if once:
                        return result
                    continue

                self._turn_id += 1
                turn = self._route_text(
                    text=command_text,
                    session_id=session_id,
                    turn_id=self._turn_id,
                    no_sound=no_sound,
                )
                turns.append(turn)
                self._enter_followup()
                if once:
                    return success(completed=True, turns=turns, wake_match=match.matched)
        finally:
            if pre_roll_source is not None:
                pre_roll_source.stop()

    def _remaining_timeout(self, deadline: float | None) -> float | None:
        if deadline is None:
            return None
        return max(0.0, deadline - time.monotonic())

    def _in_followup(self) -> bool:
        return time.monotonic() < self._followup_until

    def _enter_followup(self) -> None:
        wake_cfg = self.config.get("converse", {}).get("wakeword", {})
        timeout = float(wake_cfg.get("followup_timeout_sec", 10.0))
        self._followup_until = time.monotonic() + timeout

    def _wait_for_trigger(self, timeout: float | None) -> bool:
        wake_cfg = self.config.get("converse", {}).get("wakeword", {})
        driver_name = str(wake_cfg.get("driver") or "su03t_gpio")
        driver = get_driver("wakeword", driver_name, wake_cfg)
        driver.start()
        try:
            return bool(driver.wait_hit(timeout=float(timeout if timeout is not None else 1.0)))
        finally:
            driver.stop()

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
                max_duration_sec=3600.0,
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
    ) -> dict[str, Any]:
        return ConverseCapability(self.config).route_text(
            text,
            session_id=session_id,
            turn_id=turn_id,
            no_sound=no_sound,
        )
