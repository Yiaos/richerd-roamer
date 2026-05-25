# SU-03T Wakeword Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build hands-free `roamer wake` support using SU-03T GPIO trigger, Silero endpointing, ASR wake phrase confirmation, and existing Converse routing.

**Architecture:** Add a new wake loop beside the existing `converse` command. SU-03T only wakes the Pi-side software path; Roamer records with pre-roll, confirms speech with Silero, transcribes with the existing ASR driver, strips the wake phrase, and routes command text through `ConverseCapability.route_text()`.

**Tech Stack:** Python 3.11, Click, pytest, ALSA `arecord`, Silero VAD, FunASR, optional `gpiod>=2.0`, systemd.

---

## File Structure

- `src/roamer/plugins/interaction/services/wake_phrases.py`: normalize ASR text and strip `Richard` / `Rich-erd` / `瑞彻德` from the utterance prefix.
- `src/roamer/plugins/interaction/capabilities/converse.py`: extract existing per-turn routing into `route_text()` so manual `converse` and wake mode share intent, Discord fallback, and TTS behavior.
- `src/roamer/plugins/interaction/services/utterance.py`: reusable helper that records from a chunk iterator with `EndpointRecorder`, then runs ASR on the resulting WAV.
- `src/roamer/plugins/interaction/services/preroll_audio.py`: background microphone ring buffer with `capture_iter()` for pre-roll plus live chunks.
- `src/roamer/plugins/interaction/drivers/wakeword/su03t_gpio.py`: GPIO edge driver for SU-03T OUT on BCM17.
- `src/roamer/plugins/interaction/capabilities/wake.py`: runtime wake state machine.
- `src/roamer/plugins/interaction/actions/wake.py`: action wrapper matching existing plugin patterns.
- `src/roamer/cli/main.py`: add `roamer wake`.
- `src/roamer/plugins/interaction/plugin.py`: register `wake`.
- `src/roamer/platform/config.py`, `config.yaml`, `config.example.yaml`, `pyproject.toml`: defaults and optional GPIO dependency.
- `systemd/roamer-wake.service`, `install.sh`, `README.md`: service and installation flow.
- Tests under `tests/plugins/interaction/` and `tests/cli/` mirror these components.

---

## Task 1: Wake Phrase Matcher

**Files:**
- Create: `src/roamer/plugins/interaction/services/wake_phrases.py`
- Test: `tests/plugins/interaction/test_wake_phrases.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/plugins/interaction/test_wake_phrases.py`:

```python
from roamer.plugins.interaction.services.wake_phrases import match_wake_phrase


PHRASES = ["richard", "rich erd", "瑞彻德"]


def test_match_english_richard_prefix() -> None:
    match = match_wake_phrase("Richard 现在几点了", PHRASES)

    assert match.matched is True
    assert match.phrase == "richard"
    assert match.command_text == "现在几点了"


def test_match_hyphenated_rich_erd_prefix() -> None:
    match = match_wake_phrase("rich-erd 回家", PHRASES)

    assert match.matched is True
    assert match.phrase == "rich erd"
    assert match.command_text == "回家"


def test_match_chinese_prefix() -> None:
    match = match_wake_phrase("瑞彻德 看一下", PHRASES)

    assert match.matched is True
    assert match.phrase == "瑞彻德"
    assert match.command_text == "看一下"


def test_reject_non_prefix_wake_phrase() -> None:
    match = match_wake_phrase("现在叫 Richard 吗", PHRASES)

    assert match.matched is False
    assert match.phrase is None
    assert match.command_text == "现在叫 Richard 吗"


def test_only_wake_phrase_returns_empty_command() -> None:
    match = match_wake_phrase("Richard", PHRASES)

    assert match.matched is True
    assert match.phrase == "richard"
    assert match.command_text == ""
```

- [ ] **Step 2: Run the tests to verify failure**

Run:

```bash
.venv/bin/pytest -q tests/plugins/interaction/test_wake_phrases.py
```

Expected: FAIL during import with `ModuleNotFoundError` or `ImportError` because `wake_phrases.py` does not exist yet.

- [ ] **Step 3: Implement the matcher**

Create `src/roamer/plugins/interaction/services/wake_phrases.py`:

```python
"""Wake phrase matching for SU-03T-triggered utterances."""

from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Sequence


@dataclass(frozen=True)
class WakeMatch:
    matched: bool
    phrase: str | None
    command_text: str


def _normalize_ascii(value: str) -> str:
    return re.sub(r"[\s\-_]+", " ", value.casefold()).strip()


def _strip_leading_noise(value: str) -> str:
    return value.lstrip(" \t\r\n,，.。!！?？:：;；")


def match_wake_phrase(text: str, phrases: Sequence[str]) -> WakeMatch:
    original = _strip_leading_noise(str(text or ""))
    normalized = _normalize_ascii(original)

    for phrase in phrases:
        canonical = str(phrase).strip()
        if not canonical:
            continue

        if re.search(r"[\u4e00-\u9fff]", canonical):
            if original.startswith(canonical):
                return WakeMatch(
                    matched=True,
                    phrase=canonical,
                    command_text=_strip_leading_noise(original[len(canonical):]).strip(),
                )
            continue

        normalized_phrase = _normalize_ascii(canonical)
        if normalized == normalized_phrase:
            return WakeMatch(matched=True, phrase=canonical, command_text="")
        if normalized.startswith(normalized_phrase + " "):
            command_start = len(original)
            phrase_pattern = re.compile(
                r"^\s*" + r"[\s\-_]*".join(re.escape(part) for part in normalized_phrase.split()),
                re.IGNORECASE,
            )
            match = phrase_pattern.match(original)
            if match:
                command_start = match.end()
            return WakeMatch(
                matched=True,
                phrase=canonical,
                command_text=_strip_leading_noise(original[command_start:]).strip(),
            )

    return WakeMatch(matched=False, phrase=None, command_text=original)
```

- [ ] **Step 4: Run the tests to verify pass**

Run:

```bash
.venv/bin/pytest -q tests/plugins/interaction/test_wake_phrases.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/roamer/plugins/interaction/services/wake_phrases.py tests/plugins/interaction/test_wake_phrases.py
git commit -m "feat: add wake phrase matching"
```

---

## Task 2: Converse Text Routing Refactor

**Files:**
- Modify: `src/roamer/plugins/interaction/capabilities/converse.py`
- Test: `tests/plugins/interaction/test_converse_state_machine.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/plugins/interaction/test_converse_state_machine.py`:

```python
def test_converse_route_text_handles_local_intent_without_listen() -> None:
    cap = ConverseCapability(_base_config())
    calls = []

    def _run_action(name: str, **kwargs):
        calls.append((name, kwargs))
        if name == "speak":
            return {"ok": True, "played": True, "text": kwargs["text"]}
        return {"ok": True}

    with patch(
        "roamer.plugins.interaction.capabilities.converse.run_action", side_effect=_run_action
    ):
        turn = cap.route_text(
            "现在几点",
            session_id="session1",
            turn_id=1,
            no_sound=False,
        )

    assert turn["turn_id"] == 1
    assert turn["text"] == "现在几点"
    assert turn["matched"] is True
    assert turn["route"] == "local"
    assert turn["action"] == "time.now"
    assert [name for name, _ in calls] == ["speak"]


def test_converse_route_text_handles_discord_fallback_without_listen() -> None:
    cap = ConverseCapability(_base_config())

    with patch(
        "roamer.plugins.interaction.capabilities.converse.send_fallback",
        return_value={"ok": True, "sent": True},
    ) as fallback:
        turn = cap.route_text(
            "讲个笑话",
            session_id="session2",
            turn_id=2,
            no_sound=True,
        )

    assert turn["turn_id"] == 2
    assert turn["route"] == "discord"
    assert turn["fallback"] == {"ok": True, "sent": True}
    fallback.assert_called_once()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/pytest -q tests/plugins/interaction/test_converse_state_machine.py::test_converse_route_text_handles_local_intent_without_listen tests/plugins/interaction/test_converse_state_machine.py::test_converse_route_text_handles_discord_fallback_without_listen
```

Expected: FAIL with `AttributeError: 'ConverseCapability' object has no attribute 'route_text'`.

- [ ] **Step 3: Extract `route_text()`**

Modify `src/roamer/plugins/interaction/capabilities/converse.py`:

```python
    def route_text(
        self,
        text: str,
        *,
        session_id: str,
        turn_id: int,
        no_sound: bool,
    ) -> dict[str, Any]:
        converse_cfg = self.config.get("converse", {})
        intents = converse_cfg.get("intents", [])
        discord_cfg = converse_cfg.get("discord", {})
        normalized_text = str(text or "").strip()
        intent_result = match_intent(normalized_text, intents)
        if not intent_result.get("ok"):
            return {
                "turn_id": turn_id,
                "stage": "intent",
                "ok": False,
                "error_code": intent_result.get("error_code"),
                "text": normalized_text,
            }

        turn_info: dict[str, Any] = {
            "turn_id": turn_id,
            "text": normalized_text,
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
                normalized_text,
                discord_cfg=discord_cfg,
                session_id=session_id,
                turn_id=turn_id,
            )
            turn_info.update({"route": "discord", "fallback": fallback_result})

        return turn_info
```

Then replace the duplicated intent/fallback block inside `run()` with:

```python
            turn_info = self.route_text(
                text,
                session_id=session_id,
                turn_id=turn_id,
                no_sound=no_sound,
            )
            if "endpoint_metrics" in listen_result:
                turn_info["endpoint_metrics"] = listen_result["endpoint_metrics"]
            if turn_info.get("stage") == "intent" and not turn_info.get("ok", True):
                turns.append(turn_info)
                return error(
                    "converse_intent_invalid_action",
                    "Converse intent stage failed",
                    error_code=turn_info.get("error_code")
                    or ErrorCode.CONVERSE_INTENT_INVALID_ACTION,
                    session_id=session_id,
                    turn_id=turn_id,
                    turns=turns,
                )
            turns.append(turn_info)
```

Keep the existing listen failure and empty-text behavior unchanged. `route_text()` must
not call `listen`; it only routes already-transcribed text.

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/pytest -q tests/plugins/interaction/test_converse_state_machine.py tests/cli/test_converse_cli.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/roamer/plugins/interaction/capabilities/converse.py tests/plugins/interaction/test_converse_state_machine.py
git commit -m "refactor: route converse text directly"
```

---

## Task 3: Utterance Recorder Service

**Files:**
- Create: `src/roamer/plugins/interaction/services/utterance.py`
- Test: `tests/plugins/interaction/test_utterance.py`

- [ ] **Step 1: Write failing service tests**

Create `tests/plugins/interaction/test_utterance.py`:

```python
from pathlib import Path

from roamer.plugins.interaction.services.utterance import transcribe_chunked_utterance


def test_transcribe_chunked_utterance_calls_endpoint_and_asr(tmp_path: Path) -> None:
    output = tmp_path / "utterance.wav"
    calls = []

    class Recorder:
        def record(self):
            calls.append("record")
            output.write_bytes(b"RIFFfake")
            return {"ok": True, "audio_path": str(output), "endpoint_metrics": {"speech_duration_sec": 1.2}}

    class Asr:
        def transcribe(self, path: str):
            calls.append(("asr", path))
            return {"ok": True, "text": "Richard 现在几点了", "confidence": 0.9}

    result = transcribe_chunked_utterance(recorder=Recorder(), asr=Asr())

    assert result["ok"] is True
    assert result["text"] == "Richard 现在几点了"
    assert result["audio_path"] == str(output)
    assert result["endpoint_metrics"] == {"speech_duration_sec": 1.2}
    assert calls == ["record", ("asr", str(output))]


def test_transcribe_chunked_utterance_returns_recording_error() -> None:
    class Recorder:
        def record(self):
            return {"ok": False, "error_code": "speech.vad.no_speech"}

    class Asr:
        def transcribe(self, path: str):
            raise AssertionError("ASR should not run when recording failed")

    result = transcribe_chunked_utterance(recorder=Recorder(), asr=Asr())

    assert result == {"ok": False, "error_code": "speech.vad.no_speech"}
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/pytest -q tests/plugins/interaction/test_utterance.py
```

Expected: FAIL because `utterance.py` is missing.

- [ ] **Step 3: Implement service**

Create `src/roamer/plugins/interaction/services/utterance.py`:

```python
"""Helpers for endpointed utterance recording and transcription."""

from __future__ import annotations

from typing import Any, Protocol


class RecorderProtocol(Protocol):
    def record(self) -> dict[str, Any]:
        raise NotImplementedError


class AsrProtocol(Protocol):
    def transcribe(self, path: str) -> dict[str, Any]:
        raise NotImplementedError


def transcribe_chunked_utterance(
    *,
    recorder: RecorderProtocol,
    asr: AsrProtocol,
) -> dict[str, Any]:
    record_result = recorder.record()
    if not record_result.get("ok"):
        return record_result

    audio_path = str(record_result.get("audio_path") or record_result.get("path") or "")
    asr_result = asr.transcribe(audio_path)
    if not asr_result.get("ok"):
        return asr_result

    result = {
        "ok": True,
        "text": asr_result.get("text", ""),
        "confidence": asr_result.get("confidence"),
        "audio_path": audio_path,
    }
    if "endpoint_metrics" in record_result:
        result["endpoint_metrics"] = record_result["endpoint_metrics"]
    return result
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/pytest -q tests/plugins/interaction/test_utterance.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/roamer/plugins/interaction/services/utterance.py tests/plugins/interaction/test_utterance.py
git commit -m "feat: add utterance transcription helper"
```

---

## Task 4: Pre-Roll Audio Source

**Files:**
- Create: `src/roamer/plugins/interaction/services/preroll_audio.py`
- Test: `tests/plugins/interaction/test_preroll_audio.py`

- [ ] **Step 1: Write failing tests**

Create `tests/plugins/interaction/test_preroll_audio.py`:

```python
from roamer.plugins.interaction.services.preroll_audio import PreRollAudioSource


def test_preroll_snapshot_keeps_bounded_recent_chunks() -> None:
    source = PreRollAudioSource(
        chunk_source=iter([b"a", b"b", b"c", b"d"]),
        chunk_duration_sec=0.1,
        pre_roll_sec=0.25,
    )

    source.drain_for_test()

    assert source.snapshot() == [b"b", b"c", b"d"]


def test_capture_iter_yields_snapshot_then_live_chunks() -> None:
    source = PreRollAudioSource(
        chunk_source=iter([b"a", b"b", b"c"]),
        chunk_duration_sec=0.1,
        pre_roll_sec=0.2,
    )

    source.drain_for_test(count=3)
    capture = source.capture_iter(max_duration_sec=0.3)

    assert next(capture) == b"b"
    assert next(capture) == b"c"

    source.append_for_test(b"d")

    assert next(capture) == b"d"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/pytest -q tests/plugins/interaction/test_preroll_audio.py
```

Expected: FAIL because `preroll_audio.py` is missing.

- [ ] **Step 3: Implement pre-roll source**

Create `src/roamer/plugins/interaction/services/preroll_audio.py`:

```python
"""Pre-roll audio buffering for GPIO-triggered wake capture."""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Iterable, Iterator


class PreRollAudioSource:
    def __init__(
        self,
        *,
        chunk_source: Iterable[bytes],
        chunk_duration_sec: float,
        pre_roll_sec: float,
    ):
        self._chunk_source = iter(chunk_source)
        maxlen = max(1, int(round(pre_roll_sec / chunk_duration_sec)))
        self._buffer: deque[tuple[int, bytes]] = deque(maxlen=maxlen)
        self._chunk_duration_sec = float(chunk_duration_sec)
        self._condition = threading.Condition()
        self._thread: threading.Thread | None = None
        self._stopped = threading.Event()
        self._source_ended = False
        self._next_seq = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stopped.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def snapshot(self) -> list[bytes]:
        with self._condition:
            return [chunk for _, chunk in self._buffer]

    def capture_iter(self, max_duration_sec: float) -> Iterator[bytes]:
        with self._condition:
            snapshot = list(self._buffer)
            next_seq = self._next_seq
        yield from self.chunks_after_snapshot(snapshot, next_seq, max_duration_sec)

    def chunks_after_snapshot(
        self,
        snapshot: list[tuple[int, bytes]],
        next_seq: int,
        max_duration_sec: float,
    ) -> Iterator[bytes]:
        yielded = 0
        max_chunks = max(1, int(round(max_duration_sec / self._chunk_duration_sec)))
        for _, chunk in snapshot:
            yielded += 1
            yield chunk
            if yielded >= max_chunks:
                return
        while yielded < max_chunks:
            with self._condition:
                while (
                    not self._stopped.is_set()
                    and not self._source_ended
                    and self._next_seq <= next_seq
                ):
                    self._condition.wait(timeout=0.1)
                live = [(seq, chunk) for seq, chunk in self._buffer if seq >= next_seq]
                if not live:
                    return
                seq, chunk = live[0]
                next_seq = seq + 1
            yielded += 1
            yield chunk

    def append_for_test(self, chunk: bytes) -> None:
        self._append_chunk(chunk)

    def drain_for_test(self, count: int | None = None) -> None:
        drained = 0
        while count is None or drained < count:
            try:
                chunk = next(self._chunk_source)
            except StopIteration:
                return
            self._append_chunk(chunk)
            drained += 1

    def _run(self) -> None:
        while not self._stopped.is_set():
            try:
                chunk = next(self._chunk_source)
            except StopIteration:
                with self._condition:
                    self._source_ended = True
                    self._condition.notify_all()
                return
            self._append_chunk(chunk)

    def _append_chunk(self, chunk: bytes) -> None:
        with self._condition:
            self._buffer.append((self._next_seq, chunk))
            self._next_seq += 1
            self._condition.notify_all()
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/pytest -q tests/plugins/interaction/test_preroll_audio.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/roamer/plugins/interaction/services/preroll_audio.py tests/plugins/interaction/test_preroll_audio.py
git commit -m "feat: add wake audio pre-roll buffer"
```

---

## Task 5: SU-03T GPIO Driver

**Files:**
- Create: `src/roamer/plugins/interaction/drivers/wakeword/su03t_gpio.py`
- Modify: `src/roamer/plugins/interaction/drivers/wakeword/__init__.py`
- Modify: `pyproject.toml`
- Test: `tests/plugins/interaction/test_su03t_gpio_driver.py`

- [ ] **Step 1: Write failing tests**

Create `tests/plugins/interaction/test_su03t_gpio_driver.py`:

```python
from roamer.plugins.interaction.drivers.wakeword.su03t_gpio import Su03tGpioDriver


class FakeLine:
    def __init__(self):
        self.events = [True]
        self.released = False

    def wait_edge_events(self, timeout: float):
        return bool(self.events)

    def read_edge_events(self):
        self.events.pop(0)
        return [object()]

    def release(self):
        self.released = True


class FakeChip:
    def __init__(self, path: str):
        self.path = path
        self.line = FakeLine()

    def request_lines(self, config, consumer: str):
        return self.line

    def close(self):
        return None


def test_su03t_gpio_wait_hit_uses_injected_chip_factory() -> None:
    chips = []

    def chip_factory(path: str):
        chip = FakeChip(path)
        chips.append(chip)
        return chip

    driver = Su03tGpioDriver(
        {
            "gpio_chip": "gpiochip0",
            "gpio_line": 17,
            "edge": "rising",
            "debounce_ms": 0,
            "min_interval_sec": 0,
            "chip_factory": chip_factory,
        }
    )

    driver.start()
    try:
        assert driver.wait_hit(timeout=0.1) is True
    finally:
        driver.stop()

    assert chips[0].path == "/dev/gpiochip0"
    assert chips[0].line.released is True
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/pytest -q tests/plugins/interaction/test_su03t_gpio_driver.py
```

Expected: FAIL because `su03t_gpio.py` is missing.

- [ ] **Step 3: Implement driver and register it**

Create `src/roamer/plugins/interaction/drivers/wakeword/su03t_gpio.py`:

```python
"""SU-03T GPIO wake trigger driver."""

from __future__ import annotations

import time
from typing import Any, Callable

from roamer.plugins.interaction.drivers.registry import register_driver
from roamer.plugins.interaction.drivers.wakeword.base import WakewordDriver


class Su03tGpioDriver(WakewordDriver):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._chip = None
        self._line = None
        self._last_hit = 0.0

    def start(self) -> None:
        chip_name = str(self.config.get("gpio_chip", "gpiochip0"))
        path = chip_name if chip_name.startswith("/dev/") else f"/dev/{chip_name}"
        chip_factory = self.config.get("chip_factory") or self._default_chip_factory
        self._chip = chip_factory(path)
        request_lines: Callable[..., Any] = getattr(self._chip, "request_lines")
        self._line = request_lines({}, consumer="roamer-su03t")

    def stop(self) -> None:
        if self._line is not None and hasattr(self._line, "release"):
            self._line.release()
        if self._chip is not None and hasattr(self._chip, "close"):
            self._chip.close()
        self._line = None
        self._chip = None

    def wait_hit(self, timeout: float) -> bool:
        if self._line is None:
            return False
        if not self._line.wait_edge_events(timeout=float(timeout)):
            return False
        events = self._line.read_edge_events()
        if not events:
            return False
        now = time.monotonic()
        min_interval = float(self.config.get("min_interval_sec", 1.5))
        if now - self._last_hit < min_interval:
            return False
        debounce_ms = float(self.config.get("debounce_ms", 300))
        if debounce_ms > 0:
            time.sleep(debounce_ms / 1000.0)
        self._last_hit = time.monotonic()
        return True

    def _default_chip_factory(self, path: str):
        try:
            import gpiod
        except ImportError as exc:
            raise RuntimeError("Python gpiod is required for su03t_gpio wake driver") from exc
        return gpiod.Chip(path)


register_driver("wakeword", "su03t_gpio", Su03tGpioDriver)
```

Modify `src/roamer/plugins/interaction/drivers/wakeword/__init__.py`:

```python
from roamer.plugins.interaction.drivers.wakeword.openwakeword import OpenWakewordDriver
from roamer.plugins.interaction.drivers.wakeword.su03t_gpio import Su03tGpioDriver

__all__ = ["OpenWakewordDriver", "Su03tGpioDriver"]
```

Modify `pyproject.toml`:

```toml
[project.optional-dependencies]
speech = ["torch>=2.0", "torchaudio>=2.0", "funasr>=1.0", "onnxruntime>=1.15"]
gpio = ["gpiod>=2.0"]
dev = ["pytest>=7.0", "pytest-cov>=4.0", "ruff>=0.1"]
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/pytest -q tests/plugins/interaction/test_su03t_gpio_driver.py tests/plugins/interaction/test_wakeword_driver.py
.venv/bin/ruff check src/roamer/plugins/interaction/drivers/wakeword/su03t_gpio.py src/roamer/plugins/interaction/drivers/wakeword/__init__.py tests/plugins/interaction/test_su03t_gpio_driver.py
```

Expected: PASS and `All checks passed!`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/roamer/plugins/interaction/drivers/wakeword/__init__.py src/roamer/plugins/interaction/drivers/wakeword/su03t_gpio.py tests/plugins/interaction/test_su03t_gpio_driver.py
git commit -m "feat: add SU-03T GPIO wake driver"
```

---

## Task 6: Wake Capability, Action, and CLI

**Files:**
- Create: `src/roamer/plugins/interaction/capabilities/wake.py`
- Create: `src/roamer/plugins/interaction/actions/wake.py`
- Modify: `src/roamer/plugins/interaction/plugin.py`
- Modify: `src/roamer/cli/main.py`
- Test: `tests/plugins/interaction/test_wake_capability.py`
- Test: `tests/cli/test_wake_cli.py`

- [ ] **Step 1: Write failing tests**

Create `tests/plugins/interaction/test_wake_capability.py`:

```python
from unittest.mock import Mock, patch

from roamer.plugins.interaction.capabilities.wake import WakeCapability


def _wake_config() -> dict:
    return {
        "converse": {
            "wakeword": {
                "enabled": True,
                "driver": "su03t_gpio",
                "phrases": ["richard", "rich erd", "瑞彻德"],
                "followup_timeout_sec": 10.0,
            },
            "endpoint": {"max_record_sec": 8.0},
            "intents": [{"name": "time_now", "action": "time.now", "patterns": ["几点"]}],
            "discord": {"enabled": False},
        }
    }


def test_wake_once_routes_stripped_command() -> None:
    cap = WakeCapability(_wake_config())
    wake_driver = Mock()
    wake_driver.wait_hit.return_value = True
    pre_roll_source = Mock()

    with patch(
        "roamer.plugins.interaction.capabilities.wake.get_driver",
        return_value=wake_driver,
    ), patch.object(
        cap,
        "_build_pre_roll_source",
        return_value=(pre_roll_source, Mock()),
    ), patch.object(
        cap,
        "_transcribe_once",
        return_value={"ok": True, "text": "Richard 现在几点了"},
    ), patch(
        "roamer.plugins.interaction.capabilities.wake.ConverseCapability"
    ) as converse_cls:
        converse = converse_cls.return_value
        converse.route_text.return_value = {"turn_id": 1, "text": "现在几点了", "route": "local"}

        result = cap.run(once=True, timeout=1.0, no_sound=True)

    assert result["ok"] is True
    assert result["completed"] is True
    assert result["turns"] == [{"turn_id": 1, "text": "现在几点了", "route": "local"}]
    pre_roll_source.start.assert_called_once()
    pre_roll_source.stop.assert_called_once()
    converse.route_text.assert_called_once()


def test_wake_once_ignores_non_wake_phrase() -> None:
    cap = WakeCapability(_wake_config())
    wake_driver = Mock()
    wake_driver.wait_hit.return_value = True
    pre_roll_source = Mock()

    with patch(
        "roamer.plugins.interaction.capabilities.wake.get_driver",
        return_value=wake_driver,
    ), patch.object(
        cap,
        "_build_pre_roll_source",
        return_value=(pre_roll_source, Mock()),
    ), patch.object(
        cap,
        "_transcribe_once",
        return_value={"ok": True, "text": "现在几点了"},
    ):
        result = cap.run(once=True, timeout=1.0, no_sound=True)

    assert result["ok"] is True
    assert result["completed"] is False
    assert result["reason"] == "wake_phrase_not_matched"
    pre_roll_source.stop.assert_called_once()
```

Create `tests/cli/test_wake_cli.py`:

```python
import json

from click.testing import CliRunner

from roamer.cli.main import main


def test_wake_cli_dispatches_action(monkeypatch) -> None:
    calls = []

    def fake_run_action(name: str, **kwargs):
        calls.append((name, kwargs))
        return {"ok": True, "completed": True, "turns": []}

    monkeypatch.setattr("roamer.cli.main.run_action", fake_run_action)

    result = CliRunner().invoke(main, ["wake", "--once", "--timeout", "3", "--no-sound"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["command"] == "wake"
    assert calls == [("wake", {"once": True, "timeout": 3.0, "no_sound": True})]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/pytest -q tests/plugins/interaction/test_wake_capability.py tests/cli/test_wake_cli.py
```

Expected: FAIL because `WakeCapability` and CLI command do not exist.

- [ ] **Step 3: Implement wake action and capability**

Create `src/roamer/plugins/interaction/actions/wake.py`:

```python
"""Wake action wrapper for SU-03T hands-free mode."""

from typing import Any


class WakeAction:
    def __init__(self, config: dict[str, Any]):
        from roamer.plugins.interaction.capabilities.wake import WakeCapability

        self._capability = WakeCapability(config)

    def run(
        self,
        once: bool = False,
        timeout: float | None = None,
        no_sound: bool = False,
    ) -> dict[str, Any]:
        return self._capability.run(once=once, timeout=timeout, no_sound=no_sound)
```

Create `src/roamer/plugins/interaction/capabilities/wake.py`:

```python
"""SU-03T wake loop capability."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import roamer.plugins.interaction.drivers.speech  # noqa: F401
from roamer.platform.output import success
from roamer.platform.config import get_driver_config, get_driver_name
from roamer.plugins.interaction.capabilities.base import Capability
from roamer.plugins.interaction.capabilities.converse import ConverseCapability
from roamer.plugins.interaction.capabilities.audio import AudioCapability
from roamer.plugins.interaction.drivers.registry import get_driver
from roamer.plugins.interaction.services.endpointing import (
    ChunkVadAdapter,
    EndpointConfig,
    EndpointRecorder,
)
from roamer.plugins.interaction.services.preroll_audio import PreRollAudioSource
from roamer.plugins.interaction.services.utterance import transcribe_chunked_utterance
from roamer.plugins.interaction.services.wake_phrases import match_wake_phrase


class WakeCapability(Capability):
    def _build_pre_roll_source(self, *, timeout: float) -> tuple[PreRollAudioSource, EndpointConfig]:
        endpoint_config = EndpointConfig.from_config(self.config, timeout=timeout)
        wake_cfg = self.config.get("converse", {}).get("wakeword", {})
        pre_roll_source = PreRollAudioSource(
            chunk_source=AudioCapability(self.config).stream_chunks(
                chunk_duration_sec=endpoint_config.chunk_duration_sec,
                max_duration_sec=24 * 60 * 60,
            ),
            chunk_duration_sec=endpoint_config.chunk_duration_sec,
            pre_roll_sec=float(wake_cfg.get("pre_roll_sec", 0.8)),
        )
        return pre_roll_source, endpoint_config

    def _transcribe_once(
        self,
        *,
        pre_roll_source: PreRollAudioSource,
        endpoint_config: EndpointConfig,
    ) -> dict[str, Any]:
        audio_path = f"/tmp/roamer_wake_{uuid.uuid4().hex}.wav"
        vad_name = get_driver_name(self.config, "vad")
        vad = get_driver("vad", vad_name, get_driver_config(self.config, vad_name))
        asr_name = get_driver_name(self.config, "asr")
        asr = get_driver("asr", asr_name, get_driver_config(self.config, asr_name))
        recorder = EndpointRecorder(
            chunk_source=pre_roll_source.capture_iter(endpoint_config.max_record_sec),
            vad_probability=ChunkVadAdapter(
                vad,
                threshold=endpoint_config.threshold,
            ).probability,
            config=endpoint_config,
            output_path=audio_path,
        )
        try:
            return transcribe_chunked_utterance(recorder=recorder, asr=asr)
        finally:
            Path(audio_path).unlink(missing_ok=True)

    def run(
        self,
        *,
        once: bool = False,
        timeout: float | None = None,
        no_sound: bool = False,
    ) -> dict[str, Any]:
        converse_cfg = self.config.get("converse", {})
        wake_cfg = converse_cfg.get("wakeword", {})
        driver_name = str(wake_cfg.get("driver") or "su03t_gpio")
        wait_timeout = float(timeout if timeout is not None else converse_cfg.get("silence_timeout", 8.0))
        phrases = list(wake_cfg.get("phrases") or ["richard", "rich erd", "瑞彻德"])
        session_id = uuid.uuid4().hex[:12]
        turns: list[dict[str, Any]] = []
        pre_roll_source, endpoint_config = self._build_pre_roll_source(timeout=wait_timeout)

        driver = get_driver("wakeword", driver_name, wake_cfg)
        driver.start()
        pre_roll_source.start()
        try:
            while True:
                if not driver.wait_hit(timeout=wait_timeout):
                    return success(
                        completed=False,
                        session_id=session_id,
                        turns=turns,
                        reason="wake_timeout",
                    )

                transcript_result = self._transcribe_once(
                    pre_roll_source=pre_roll_source,
                    endpoint_config=endpoint_config,
                )
                if not transcript_result.get("ok"):
                    return transcript_result

                match = match_wake_phrase(str(transcript_result.get("text") or ""), phrases)
                if not match.matched:
                    if once:
                        return success(
                            completed=False,
                            session_id=session_id,
                            turns=turns,
                            reason="wake_phrase_not_matched",
                            text=transcript_result.get("text", ""),
                        )
                    continue

                if not match.command_text:
                    if once:
                        return success(
                            completed=False,
                            session_id=session_id,
                            turns=turns,
                            reason="wake_phrase_only",
                        )
                    continue

                turn = ConverseCapability(self.config).route_text(
                    match.command_text,
                    session_id=session_id,
                    turn_id=len(turns) + 1,
                    no_sound=no_sound,
                )
                turns.append(turn)
                if once:
                    return success(completed=True, session_id=session_id, turns=turns)
        finally:
            pre_roll_source.stop()
            driver.stop()
```

This implementation intentionally does not call `run_action("listen")`: wake mode owns
the microphone through `PreRollAudioSource`, so pre-roll audio is preserved after the
SU-03T GPIO edge. When `roamer-wake.service` is enabled, users should treat `roamer wake`
as the primary hands-free microphone owner and stop the service before running manual
long-lived microphone commands for debugging.

Modify `src/roamer/plugins/interaction/plugin.py`:

```python
from roamer.plugins.interaction.actions.wake import WakeAction
```

Register it:

```python
    registry.register("wake", _lazy_runner(WakeAction, config))
```

Modify `_ensure_interaction_plugin_registered()` in `src/roamer/cli/main.py` to remove `wake`, and add CLI:

```python
@main.command()
@click.option("--once", is_flag=True, help="Handle one wake command and exit")
@click.option("--timeout", type=float, default=None, help="Wake/listen timeout in seconds")
@click.option("--no-sound", is_flag=True, help="Disable spoken responses")
@click.pass_context
def wake(
    ctx: click.Context,
    once: bool,
    timeout: float | None,
    no_sound: bool,
) -> None:
    """Run SU-03T hands-free wake loop."""
    _ensure_interaction_plugin_registered(ctx.obj["config"])
    result = run_action("wake", once=once, timeout=timeout, no_sound=no_sound)
    emit_contract_result(ctx, "wake", result)
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/pytest -q tests/plugins/interaction/test_wake_capability.py tests/cli/test_wake_cli.py tests/plugins/interaction/test_plugin_registration.py
.venv/bin/ruff check src/roamer/cli/main.py src/roamer/plugins/interaction/actions/wake.py src/roamer/plugins/interaction/capabilities/wake.py src/roamer/plugins/interaction/plugin.py tests/plugins/interaction/test_wake_capability.py tests/cli/test_wake_cli.py
```

Expected: PASS and `All checks passed!`.

- [ ] **Step 5: Commit**

```bash
git add src/roamer/cli/main.py src/roamer/plugins/interaction/actions/wake.py src/roamer/plugins/interaction/capabilities/wake.py src/roamer/plugins/interaction/plugin.py tests/plugins/interaction/test_wake_capability.py tests/cli/test_wake_cli.py
git commit -m "feat: add SU-03T wake command"
```

---

## Task 7: Config, Service, and Installer

**Files:**
- Modify: `src/roamer/platform/config.py`
- Modify: `config.yaml`
- Modify: `config.example.yaml`
- Create: `systemd/roamer-wake.service`
- Modify: `install.sh`
- Modify: `README.md`
- Test: `tests/platform/test_config.py`

- [ ] **Step 1: Write failing config test**

Append to `tests/platform/test_config.py`:

```python
def test_default_config_includes_su03t_wake_defaults() -> None:
    from roamer.platform.config import DEFAULT_CONFIG

    wakeword = DEFAULT_CONFIG["converse"]["wakeword"]

    assert wakeword["driver"] == "su03t_gpio"
    assert wakeword["gpio_chip"] == "gpiochip0"
    assert wakeword["gpio_line"] == 17
    assert wakeword["edge"] == "rising"
    assert wakeword["phrases"] == ["richard", "rich erd", "瑞彻德"]
```

- [ ] **Step 2: Run config test to verify failure**

Run:

```bash
.venv/bin/pytest -q tests/platform/test_config.py::test_default_config_includes_su03t_wake_defaults
```

Expected: FAIL because defaults still point at `openwakeword`.

- [ ] **Step 3: Update defaults and service files**

Modify `src/roamer/platform/config.py` wakeword defaults to:

```python
        "wakeword": {
            "enabled": False,
            "driver": "su03t_gpio",
            "gpio_chip": "gpiochip0",
            "gpio_line": 17,
            "edge": "rising",
            "pull": "down",
            "debounce_ms": 300,
            "min_interval_sec": 1.5,
            "pre_roll_sec": 0.8,
            "ignore_while_speaking": True,
            "prompt_sound": False,
            "phrases": ["richard", "rich erd", "瑞彻德"],
            "followup_timeout_sec": 10.0,
        },
```

Update `config.yaml` and `config.example.yaml` with the same keys under `converse.wakeword`.

Create `systemd/roamer-wake.service`:

```ini
[Unit]
Description=Roamer SU-03T wake loop
After=network-online.target roamer-serve.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/richerd/worksp/richerd-roamer
ExecStart=/home/richerd/.venv/roamer/bin/roamer wake
Restart=on-failure
RestartSec=2
RuntimeDirectory=roamer
RuntimeDirectoryMode=0700
UMask=0077

[Install]
WantedBy=multi-user.target
```

Add README install section:

```markdown
### SU-03T Wake Service

Wire SU-03T as:

```text
SU-03T VCC  -> Raspberry Pi 5V, physical pin 2 or 4
SU-03T GND  -> Raspberry Pi GND, physical pin 6
SU-03T OUT  -> Raspberry Pi GPIO17 / BCM17, physical pin 11
```

Enable wake mode with `converse.wakeword.enabled: true` and `driver: su03t_gpio`.
Run `./install.sh`; it installs `roamer-wake.service` when wake mode is enabled.
```

Modify `install.sh` to install `systemd/roamer-wake.service` when config contains `driver: su03t_gpio` and `enabled: true`. Use existing service install style from `roamer-serve.service`.

- [ ] **Step 4: Run tests and shell checks**

Run:

```bash
.venv/bin/pytest -q tests/platform/test_config.py tests/cli/test_wake_cli.py
bash -n install.sh
```

Expected: PASS and no shell syntax output.

- [ ] **Step 5: Commit**

```bash
git add src/roamer/platform/config.py config.yaml config.example.yaml systemd/roamer-wake.service install.sh README.md tests/platform/test_config.py
git commit -m "feat: configure SU-03T wake service"
```

---

## Task 8: Integration Verification and Roamer Hardware Test

**Files:**
- No source edits expected; this task verifies the integrated change on local tests and Roamer hardware.

- [ ] **Step 1: Run local regression tests**

Run:

```bash
.venv/bin/pytest -q tests/plugins/interaction/test_wake_phrases.py tests/plugins/interaction/test_utterance.py tests/plugins/interaction/test_preroll_audio.py tests/plugins/interaction/test_su03t_gpio_driver.py tests/plugins/interaction/test_wake_capability.py tests/plugins/interaction/test_converse_state_machine.py tests/cli/test_wake_cli.py tests/cli/test_converse_cli.py tests/platform/test_config.py
.venv/bin/ruff check src tests
```

Expected: all selected tests pass and Ruff reports `All checks passed!`.

- [ ] **Step 2: Push and deploy to Roamer**

Run locally:

```bash
git status --short
git push origin master
```

Expected: only unrelated user-owned files may remain unstaged; push succeeds.

Run on Roamer:

```bash
ssh -o HostKeyAlias=roamer richerd@10.0.0.225 'cd /home/richerd/worksp/richerd-roamer && git pull --ff-only && ./install.sh'
```

Expected: install completes, `roamer-serve.service` remains active, and `roamer-wake.service` is installed when wake mode is enabled.

- [ ] **Step 3: Verify one-shot wake path**

Run on Roamer:

```bash
ssh -t -o HostKeyAlias=roamer richerd@10.0.0.225 'cd /home/richerd/worksp/richerd-roamer && roamer wake --once --timeout 30'
```

Expected after saying `Richard 现在几点了`: JSON with `ok: true`, `completed: true`, first turn text `现在几点了`, route `local`, action `time.now`, and a spoken reply.

- [ ] **Step 4: Verify service mode**

Run on Roamer:

```bash
ssh -o HostKeyAlias=roamer richerd@10.0.0.225 'sudo systemctl restart roamer-wake.service && systemctl is-active roamer-wake.service && journalctl -u roamer-wake.service -n 50 --no-pager'
```

Expected: `active` and logs showing wake loop startup. No repeated self-trigger loop after Roamer speaks.

- [ ] **Step 5: Record verification result in final handoff**

Report the measured hardware result in the final implementation handoff:

```text
Local tests: <pytest result>, <ruff result>
Roamer deploy: <install result>
One-shot wake: <pass/fail, phrase used, observed JSON route/action>
Service mode: <active/inactive, relevant journal line>
```

---

## Self-Review

Spec coverage:

- Hardware wiring is covered in Task 7 README/service/config and Task 8 hardware verification.
- GPIO trigger is covered in Task 5.
- Pre-roll recording is covered in Task 4.
- Silero endpointing and ASR reuse are covered in Task 3 and Task 6.
- Wake phrase variants are covered in Task 1 and Task 6.
- Existing converse routing is covered in Task 2.
- systemd and install flow are covered in Task 7.
- Hardware acceptance testing is covered in Task 8.

Placeholder scan:

- The plan does not contain `TBD`, `TODO`, or open-ended implementation instructions.
- Code tasks include concrete file paths, test snippets, commands, expected failures, and commit commands.

Type consistency:

- `WakeMatch`, `match_wake_phrase()`, `PreRollAudioSource.capture_iter()`, `Su03tGpioDriver`, `WakeCapability.run()`, `WakeAction.run()`, and `ConverseCapability.route_text()` are named consistently across tasks.
