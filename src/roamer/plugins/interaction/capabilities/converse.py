"""Converse capability (R1/R2) for interaction plugin."""

from __future__ import annotations

import datetime as dt
import threading
import uuid
from typing import Any

from roamer.platform.contract import ErrorCode
from roamer.platform.output import error, success
from roamer.platform.plugin_registry import registry
from roamer.platform.runtime import run_action
from roamer.plugins.interaction.capabilities.base import Capability
from roamer.plugins.interaction.drivers.registry import get_driver
from roamer.plugins.interaction.services.discord_client import send_fallback
from roamer.plugins.interaction.services.intent import match_intent
from roamer.plugins.motion.plugin import register as register_motion_plugin
from roamer.plugins.perception.plugin import register as register_perception_plugin


class ConverseCapability(Capability):
    """Single-process converse state machine."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._audio_lock = threading.Lock()

    def _safe_listen(self, timeout: float, *, use_endpointing: bool = False) -> dict[str, Any]:
        with self._audio_lock:
            return run_action(
                "listen",
                timeout=timeout,
                save_audio=None,
                debug=False,
                use_endpointing=use_endpointing,
            )

    def _safe_speak(self, text: str, no_sound: bool) -> dict[str, Any]:
        if no_sound:
            return success(skipped=True, reason="no_sound")
        with self._audio_lock:
            return run_action("speak", text=text, save_path=None, play=True, style=None)

    def _ensure_local_intent_actions_registered(self) -> None:
        """Register non-interaction actions that local intents may dispatch."""
        for action_name in (
            "watch",
            "sense",
            "motion.status",
            "motion.position",
            "motion.locate",
            "motion.home",
            "motion.goto",
        ):
            registry.remove(action_name)
        register_perception_plugin(registry, self.config)
        register_motion_plugin(registry, self.config)

    def _fallback_via_discord(
        self,
        text: str,
        *,
        discord_cfg: dict[str, Any],
        session_id: str,
        turn_id: int,
    ) -> dict[str, Any]:
        return send_fallback(
            text,
            config={"discord": discord_cfg},
            session_id=session_id,
            turn_id=turn_id,
            timeout_sec=3.0,
        )

    def _wait_wakeword(self, wakeword_cfg: dict[str, Any], timeout: float) -> dict[str, Any]:
        if not wakeword_cfg.get("enabled", True):
            return success(triggered=True, skipped=True, reason="wakeword_disabled")

        try:
            driver_name = str(wakeword_cfg.get("driver") or "openwakeword")
            driver_cfg = {
                "model": wakeword_cfg.get("model", ""),
                "threshold": wakeword_cfg.get("threshold", 0.5),
            }
            driver = get_driver("wakeword", driver_name, driver_cfg)
            driver.start()
            try:
                hit = driver.wait_hit(timeout=timeout)
            finally:
                driver.stop()
            return success(triggered=bool(hit), timeout=timeout)
        except Exception as exc:
            return error(
                "converse_wakeword_unavailable",
                f"Wakeword driver unavailable: {exc}",
                error_code=ErrorCode.CONVERSE_WAKEWORD_UNAVAILABLE,
            )

    def route_text(
        self,
        text: str,
        *,
        session_id: str,
        turn_id: int,
        no_sound: bool,
    ) -> dict[str, Any]:
        """Route already-transcribed text through converse intent/fallback handling."""
        converse_cfg = self.config.get("converse", {})
        intents = converse_cfg.get("intents", [])
        discord_cfg = converse_cfg.get("discord", {})

        intent_result = match_intent(text, intents)
        if not intent_result.get("ok"):
            return {
                "turn_id": turn_id,
                "stage": "intent",
                "ok": False,
                "error_code": intent_result.get("error_code"),
                "text": text,
                "intent_result": intent_result,
            }

        turn_info: dict[str, Any] = {
            "turn_id": turn_id,
            "text": text,
            "matched": bool(intent_result.get("matched")),
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        }

        if intent_result.get("matched"):
            action = str(intent_result.get("action"))
            if action == "time.now":
                now_text = dt.datetime.now().strftime("现在是 %H:%M")
                speak_result = self._safe_speak(now_text, no_sound=no_sound)
                turn_info.update({"route": "local", "action": action, "speak": speak_result})
            elif action == "remind.schedule":
                slots = dict(intent_result.get("slots") or {})
                action_result = run_action(
                    "remind",
                    delay_sec=float(slots.get("delay_sec", 0)),
                    text=str(slots.get("text") or "提醒"),
                )
                turn_info.update(
                    {
                        "route": "local",
                        "action": action,
                        "slots": slots,
                        "action_result": action_result,
                    }
                )
                if action_result.get("ok"):
                    self._safe_speak("好，已设置提醒", no_sound=no_sound)
            else:
                self._ensure_local_intent_actions_registered()
                action_result = run_action(action)
                turn_info.update(
                    {
                        "route": "local",
                        "action": action,
                        "action_result": action_result,
                    }
                )
                if action_result.get("ok"):
                    self._safe_speak(f"已执行 {action}", no_sound=no_sound)
        else:
            fallback_result = self._fallback_via_discord(
                text,
                discord_cfg=discord_cfg,
                session_id=session_id,
                turn_id=turn_id,
            )
            turn_info.update({"route": "discord", "fallback": fallback_result})

        return turn_info

    def run(
        self,
        *,
        no_wakeword: bool = False,
        timeout: float = 8.0,
        no_sound: bool = False,
        max_turns: int = 10,
        use_endpointing: bool = False,
    ) -> dict[str, Any]:
        converse_cfg = self.config.get("converse", {})
        wakeword_cfg = converse_cfg.get("wakeword", {})

        session_id = uuid.uuid4().hex[:12]
        turns: list[dict[str, Any]] = []

        if not no_wakeword:
            wake = self._wait_wakeword(wakeword_cfg, timeout=timeout)
            if not wake.get("ok"):
                return wake
            if not wake.get("triggered"):
                return success(
                    completed=True,
                    session_id=session_id,
                    mode="wakeword",
                    turns=[],
                    reason="wakeword_timeout",
                )
            if bool(wakeword_cfg.get("prompt_sound", True)) and not no_sound:
                self._safe_speak("在", no_sound=False)

        for turn_id in range(1, max_turns + 1):
            listen_result = self._safe_listen(timeout=timeout, use_endpointing=use_endpointing)
            if not listen_result.get("ok"):
                turn_error: dict[str, Any] = {
                    "turn_id": turn_id,
                    "stage": "listen",
                    "ok": False,
                    "error_code": listen_result.get("error_code"),
                }
                if "endpoint_metrics" in listen_result:
                    turn_error["endpoint_metrics"] = listen_result["endpoint_metrics"]
                turns.append(turn_error)
                error_payload: dict[str, Any] = {
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "turns": turns,
                }
                if "endpoint_metrics" in listen_result:
                    error_payload["endpoint_metrics"] = listen_result["endpoint_metrics"]
                return error(
                    "converse_listen_failed",
                    "Converse listen stage failed",
                    error_code=ErrorCode.CONVERSE_LISTEN_FAILED,
                    **error_payload,
                )

            text = str(listen_result.get("text") or "").strip()
            if not text:
                turns.append({"turn_id": turn_id, "stage": "listen", "ok": True, "empty": True})
                break

            turn_info = self.route_text(
                text,
                session_id=session_id,
                turn_id=turn_id,
                no_sound=no_sound,
            )
            if not turn_info.get("ok", True):
                turns.append({k: v for k, v in turn_info.items() if k != "intent_result"})
                return dict(turn_info["intent_result"])
            if "endpoint_metrics" in listen_result:
                turn_info["endpoint_metrics"] = listen_result["endpoint_metrics"]

            turns.append(turn_info)

        return success(
            completed=True,
            session_id=session_id,
            mode="no_wakeword" if no_wakeword else "wakeword",
            max_turns=max_turns,
            turns=turns,
        )
