# SU-03T Wakeword Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement hands-free Roamer wake using SU-03T GPIO trigger, Silero endpointing, ASR wake phrase confirmation, follow-up mode, systemd installation, and hardware verification.

**Architecture:** Add a `roamer wake` service path alongside existing `roamer converse`. SU-03T provides a GPIO edge trigger only; Roamer captures pre-roll audio, runs existing Silero/FunASR, strips the wake phrase, and routes command text through the existing converse intent/fallback logic.

**Tech Stack:** Python 3.11, Click CLI, ALSA `arecord`, Silero VAD, FunASR, optional Python `gpiod`, systemd, pytest, ruff.

---

## File Map

- `src/roamer/plugins/interaction/services/wake_phrases.py`: pure wake phrase normalization, matching, and command stripping.
- `src/roamer/plugins/interaction/services/preroll_audio.py`: reusable pre-roll chunk buffer around an audio chunk source.
- `src/roamer/plugins/interaction/drivers/wakeword/su03t_gpio.py`: SU-03T GPIO edge driver behind the existing `WakewordDriver` interface.
- `src/roamer/plugins/interaction/capabilities/converse.py`: extract `route_text()` so manual converse and wake mode share routing.
- `src/roamer/plugins/interaction/capabilities/wake.py`: wake loop state machine and one-shot execution.
- `src/roamer/plugins/interaction/actions/wake.py`: action wrapper.
- `src/roamer/plugins/interaction/plugin.py`: register `wake`.
- `src/roamer/cli/main.py`: add `roamer wake`.
- `src/roamer/platform/config.py`, `config.yaml`, `config.example.yaml`: SU-03T defaults and endpoint settings.
- `pyproject.toml`: add optional GPIO dependency.
- `systemd/roamer-wake.service`: boot service.
- `install.sh`: install/validate GPIO dependency and wake service.
- `tests/...`: focused unit and CLI tests per task.

## Task 1: Wake Phrase Matcher

**Files:**
- Create: `src/roamer/plugins/interaction/services/wake_phrases.py`
- Test: `tests/plugins/interaction/test_wake_phrases.py`

- [ ] **Step 1: Write failing tests**

Create `tests/plugins/interaction/test_wake_phrases.py`:

```python
from roamer.plugins.interaction.services.wake_phrases import match_wake_phrase


PHRASES = ["richard", "rich erd", "瑞彻德"]


def test_matches_english_prefix_and_strips_command() -> None:
    result = match_wake_phrase("Richard 现在几点了", PHRASES)
    assert result.matched is True
    assert result.phrase == "richard"
    assert result.command_text == "现在几点了"


def test_matches_hyphenated_variant() -> None:
    result = match_wake_phrase("rich-erd 回家", PHRASES)
    assert result.matched is True
    assert result.phrase == "rich erd"
    assert result.command_text == "回家"


def test_matches_chinese_variant() -> None:
    result = match_wake_phrase("瑞彻德 看一下", PHRASES)
    assert result.matched is True
    assert result.phrase == "瑞彻德"
    assert result.command_text == "看一下"


def test_non_prefix_does_not_match() -> None:
    result = match_wake_phrase("现在几点了 Richard", PHRASES)
    assert result.matched is False
    assert result.command_text == "现在几点了 Richard"


def test_wake_phrase_only_returns_empty_command() -> None:
    result = match_wake_phrase(" Richard ", PHRASES)
    assert result.matched is True
    assert result.command_text == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest -q tests/plugins/interaction/test_wake_phrases.py`

Expected: FAIL with `ModuleNotFoundError` for `wake_phrases`.

- [ ] **Step 3: Implement matcher**

Create `src/roamer/plugins/interaction/services/wake_phrases.py`:

```python
"""Wake phrase matching for hands-free converse."""

from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Sequence


_LEADING_JUNK_RE = re.compile(r"^[\s,，。.!！?？:：;；、\"'“”‘’\-\_]+")
_SEPARATOR_RE = re.compile(r"[\s\-_]+")


@dataclass(frozen=True)
class WakeMatch:
    matched: bool
    phrase: str | None
    command_text: str


def _canonical_ascii(text: str) -> str:
    return _SEPARATOR_RE.sub("", text.casefold())


def _strip_prefix(original: str, length: int) -> str:
    return _LEADING_JUNK_RE.sub("", original[length:]).strip()


def match_wake_phrase(text: str, phrases: Sequence[str]) -> WakeMatch:
    original = str(text or "")
    stripped = _LEADING_JUNK_RE.sub("", original).strip()
    folded = stripped.casefold()
    compact = _canonical_ascii(stripped)

    for phrase in phrases:
        phrase_text = str(phrase or "").strip()
        if not phrase_text:
            continue

        phrase_folded = phrase_text.casefold()
        phrase_compact = _canonical_ascii(phrase_text)

        if phrase_text and phrase_text[0].isascii():
            if compact.startswith(phrase_compact):
                consumed = _ascii_consumed_length(stripped, phrase_compact)
                return WakeMatch(True, phrase_text, _strip_prefix(stripped, consumed))
            continue

        if folded.startswith(phrase_folded):
            return WakeMatch(True, phrase_text, _strip_prefix(stripped, len(phrase_text)))

    return WakeMatch(False, None, original.strip())


def _ascii_consumed_length(text: str, compact_phrase: str) -> int:
    seen = ""
    for index, char in enumerate(text):
        if re.match(r"[\s\-_]", char):
            continue
        seen += char.casefold()
        if seen == compact_phrase:
            return index + 1
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest -q tests/plugins/interaction/test_wake_phrases.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/roamer/plugins/interaction/services/wake_phrases.py tests/plugins/interaction/test_wake_phrases.py
git commit -m "feat: add wake phrase matcher"
```

## Task 2: Converse Text Routing Refactor

**Files:**
- Modify: `src/roamer/plugins/interaction/capabilities/converse.py`
- Test: `tests/plugins/interaction/test_converse_state_machine.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/plugins/interaction/test_converse_state_machine.py`:

```python
def test_converse_route_text_reuses_local_intent_flow() -> None:
    cap = ConverseCapability(_base_config())

    with patch(
        "roamer.plugins.interaction.capabilities.converse.run_action",
        return_value={"ok": True, "played": True},
    ):
        result = cap.route_text(
            "现在几点",
            session_id="s1",
            turn_id=1,
            no_sound=True,
        )

    assert result["turn_id"] == 1
    assert result["text"] == "现在几点"
    assert result["matched"] is True
    assert result["route"] == "local"
    assert result["action"] == "time.now"


def test_converse_route_text_reuses_discord_fallback_flow() -> None:
    cap = ConverseCapability(_base_config())

    with patch(
        "roamer.plugins.interaction.capabilities.converse.send_fallback",
        return_value={"ok": True, "sent": False, "skipped": True},
    ):
        result = cap.route_text(
            "讲个笑话",
            session_id="s1",
            turn_id=1,
            no_sound=True,
        )

    assert result["route"] == "discord"
    assert result["matched"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest -q tests/plugins/interaction/test_converse_state_machine.py::test_converse_route_text_reuses_local_intent_flow tests/plugins/interaction/test_converse_state_machine.py::test_converse_route_text_reuses_discord_fallback_flow`

Expected: FAIL with `AttributeError: 'ConverseCapability' object has no attribute 'route_text'`.

- [ ] **Step 3: Extract `route_text()`**

Move the intent/fallback body in `ConverseCapability.run()` into:

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

    # Preserve the existing local action and Discord fallback branches here.
    # The code moved from run() should keep the same result keys.
    return turn_info
```

Then replace the duplicated branch inside `run()` with:

```python
turn_info = self.route_text(
    text,
    session_id=session_id,
    turn_id=turn_id,
    no_sound=no_sound,
)
if not turn_info.get("ok", True):
    turns.append(turn_info)
    return dict(turn_info["intent_result"])
if "endpoint_metrics" in listen_result:
    turn_info["endpoint_metrics"] = listen_result["endpoint_metrics"]
turns.append(turn_info)
```

The implementation must preserve existing behavior and result fields from the current tests.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest -q tests/plugins/interaction/test_converse_state_machine.py tests/cli/test_converse_cli.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/roamer/plugins/interaction/capabilities/converse.py tests/plugins/interaction/test_converse_state_machine.py
git commit -m "refactor: share converse text routing"
```

## Task 3: SU-03T GPIO Driver

**Files:**
- Create: `src/roamer/plugins/interaction/drivers/wakeword/su03t_gpio.py`
- Modify: `src/roamer/plugins/interaction/drivers/wakeword/__init__.py`
- Modify: `pyproject.toml`
- Test: `tests/plugins/interaction/test_su03t_gpio_driver.py`

- [ ] **Step 1: Write fake-gpio tests**

Create `tests/plugins/interaction/test_su03t_gpio_driver.py` with fake request objects that verify timeout, debounce, and cleanup:

```python
from roamer.plugins.interaction.drivers.wakeword.su03t_gpio import Su03tGpioDriver


class FakeRequest:
    def __init__(self, events):
        self.events = list(events)
        self.released = False

    def wait_edge_events(self, timeout):
        return bool(self.events)

    def read_edge_events(self):
        if not self.events:
            return []
        return [self.events.pop(0)]

    def release(self):
        self.released = True


def test_su03t_gpio_timeout_without_event() -> None:
    request = FakeRequest([])
    driver = Su03tGpioDriver({"request_factory": lambda cfg: request})
    driver.start()
    try:
        assert driver.wait_hit(timeout=0.01) is False
    finally:
        driver.stop()
    assert request.released is True


def test_su03t_gpio_hit_with_fake_event() -> None:
    request = FakeRequest([object()])
    driver = Su03tGpioDriver({"request_factory": lambda cfg: request})
    driver.start()
    try:
        assert driver.wait_hit(timeout=0.01) is True
    finally:
        driver.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest -q tests/plugins/interaction/test_su03t_gpio_driver.py`

Expected: FAIL with `ModuleNotFoundError` for `su03t_gpio`.

- [ ] **Step 3: Implement driver**

Implement `Su03tGpioDriver` with an injectable `request_factory`. Register it:

```python
register_driver("wakeword", "su03t_gpio", Su03tGpioDriver)
```

Use lazy import for `gpiod` only inside the default request factory. Add optional dependency:

```toml
gpio = ["gpiod>=2.0"]
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest -q tests/plugins/interaction/test_su03t_gpio_driver.py tests/plugins/interaction/test_wakeword_driver.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/roamer/plugins/interaction/drivers/wakeword/__init__.py src/roamer/plugins/interaction/drivers/wakeword/su03t_gpio.py tests/plugins/interaction/test_su03t_gpio_driver.py
git commit -m "feat: add SU-03T GPIO wake driver"
```

## Task 4: Pre-Roll Audio Source

**Files:**
- Create: `src/roamer/plugins/interaction/services/preroll_audio.py`
- Test: `tests/plugins/interaction/test_preroll_audio.py`

- [ ] **Step 1: Write failing tests**

Create tests for bounded pre-roll and live chunk continuation:

```python
from roamer.plugins.interaction.services.preroll_audio import PreRollAudioSource


def test_preroll_snapshot_keeps_recent_chunks() -> None:
    source = PreRollAudioSource(
        chunk_source=iter([b"a", b"b", b"c"]),
        chunk_duration_sec=0.5,
        pre_roll_sec=1.0,
    )
    source.drain_available_for_test()
    assert source.snapshot() == [b"b", b"c"]


def test_capture_iter_yields_snapshot_then_live_chunks() -> None:
    source = PreRollAudioSource(
        chunk_source=iter([b"a", b"b", b"c", b"d"]),
        chunk_duration_sec=0.5,
        pre_roll_sec=1.0,
    )
    source.drain_available_for_test(limit=2)
    assert list(source.capture_iter(max_duration_sec=1.0)) == [b"a", b"b", b"c", b"d"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest -q tests/plugins/interaction/test_preroll_audio.py`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement source**

Implement a testable class using a bounded `deque`. The production path may run a reader
thread, but tests should be deterministic through `drain_available_for_test()`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest -q tests/plugins/interaction/test_preroll_audio.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/roamer/plugins/interaction/services/preroll_audio.py tests/plugins/interaction/test_preroll_audio.py
git commit -m "feat: add pre-roll audio source"
```

## Task 5: Wake Capability and CLI

**Files:**
- Create: `src/roamer/plugins/interaction/actions/wake.py`
- Create: `src/roamer/plugins/interaction/capabilities/wake.py`
- Modify: `src/roamer/plugins/interaction/plugin.py`
- Modify: `src/roamer/cli/main.py`
- Test: `tests/cli/test_wake_cli.py`
- Test: `tests/plugins/interaction/test_wake_capability.py`

- [ ] **Step 1: Write failing capability tests**

Create `tests/plugins/interaction/test_wake_capability.py` for one-shot match, non-match ignore, and follow-up:

```python
from unittest.mock import Mock

from roamer.plugins.interaction.capabilities.wake import WakeCapability


def _config() -> dict:
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
            "discord": {"enabled": False, "channel_id": "", "token_env": "DISCORD_BOT_TOKEN"},
        }
    }


def test_wake_once_routes_stripped_command(monkeypatch) -> None:
    cap = WakeCapability(_config())
    cap._wait_for_trigger = Mock(return_value=True)
    cap._listen_once = Mock(return_value={"ok": True, "text": "Richard 现在几点了"})
    cap._route_text = Mock(return_value={"turn_id": 1, "route": "local"})

    result = cap.run(once=True, timeout=1.0, no_sound=True)

    assert result["ok"] is True
    cap._route_text.assert_called_once()
    assert cap._route_text.call_args.kwargs["text"] == "现在几点了"


def test_wake_once_ignores_non_wake_text(monkeypatch) -> None:
    cap = WakeCapability(_config())
    cap._wait_for_trigger = Mock(return_value=True)
    cap._listen_once = Mock(return_value={"ok": True, "text": "现在几点了"})

    result = cap.run(once=True, timeout=1.0, no_sound=True)

    assert result["ok"] is True
    assert result["ignored"] is True
    assert result["reason"] == "wake_phrase_not_matched"
```

- [ ] **Step 2: Write failing CLI test**

Create `tests/cli/test_wake_cli.py`:

```python
import json
from unittest.mock import patch

from click.testing import CliRunner

from roamer.cli.main import main


def test_wake_cli_dispatches_action() -> None:
    with patch("roamer.cli.main.run_action", return_value={"ok": True, "completed": True}) as run:
        result = CliRunner().invoke(main, ["wake", "--once", "--timeout", "2", "--no-sound"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["command"] == "wake"
    run.assert_called_once_with("wake", once=True, timeout=2.0, no_sound=True)
```

- [ ] **Step 3: Run tests to verify failure**

Run: `.venv/bin/pytest -q tests/plugins/interaction/test_wake_capability.py tests/cli/test_wake_cli.py`

Expected: FAIL because wake capability and CLI do not exist.

- [ ] **Step 4: Implement wake action/capability/CLI**

Implement the minimum one-shot loop:

- `_wait_for_trigger()` uses configured wakeword driver.
- `_listen_once()` calls `run_action("listen", timeout=max_record_sec, save_audio=None, debug=False, use_endpointing=True)`.
- `_route_text()` creates `ConverseCapability(config).route_text(...)`.
- `run(once=True)` returns after one trigger.
- Infinite mode loops until interrupted.

- [ ] **Step 5: Run tests**

Run: `.venv/bin/pytest -q tests/plugins/interaction/test_wake_capability.py tests/cli/test_wake_cli.py tests/plugins/interaction/test_converse_state_machine.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/roamer/cli/main.py src/roamer/plugins/interaction/actions/wake.py src/roamer/plugins/interaction/capabilities/wake.py src/roamer/plugins/interaction/plugin.py tests/cli/test_wake_cli.py tests/plugins/interaction/test_wake_capability.py
git commit -m "feat: add SU-03T wake loop"
```

## Task 6: Configuration Defaults

**Files:**
- Modify: `src/roamer/platform/config.py`
- Modify: `config.yaml`
- Modify: `config.example.yaml`
- Test: `tests/platform/test_config.py`

- [ ] **Step 1: Write failing config test**

Add assertions to `tests/platform/test_config.py`:

```python
def test_default_su03t_wakeword_config() -> None:
    from roamer.platform.config import DEFAULT_CONFIG

    wakeword = DEFAULT_CONFIG["converse"]["wakeword"]
    assert wakeword["driver"] == "su03t_gpio"
    assert wakeword["gpio_line"] == 17
    assert wakeword["edge"] == "rising"
    assert wakeword["phrases"] == ["richard", "rich erd", "瑞彻德"]
    assert wakeword["prompt_sound"] is False
    assert DEFAULT_CONFIG["converse"]["endpoint"]["mode"] == "vad_endpoint"
```

- [ ] **Step 2: Run test to verify failure**

Run: `.venv/bin/pytest -q tests/platform/test_config.py::test_default_su03t_wakeword_config`

Expected: FAIL because defaults still use `openwakeword`.

- [ ] **Step 3: Update defaults and YAML**

Set `converse.wakeword` to the SU-03T values from the spec and set endpoint mode to
`vad_endpoint`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest -q tests/platform/test_config.py tests/cli/test_config_resolution.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/roamer/platform/config.py config.yaml config.example.yaml tests/platform/test_config.py
git commit -m "config: enable SU-03T wake defaults"
```

## Task 7: systemd and Installer

**Files:**
- Create: `systemd/roamer-wake.service`
- Modify: `install.sh`
- Modify: `README.md`
- Test: `tests/cli/test_install_docs.py` if a local installer test pattern exists; otherwise verify with shell syntax and targeted install dry-run logic.

- [ ] **Step 1: Add service file**

Create `systemd/roamer-wake.service` exactly as the spec describes, using:

```ini
ExecStart=/home/richerd/.venv/roamer/bin/roamer wake
```

- [ ] **Step 2: Extend installer**

Update `install.sh` to:

- install `.[speech,gpio]` instead of only speech extras;
- copy `systemd/roamer-wake.service` into `/etc/systemd/system/`;
- run `systemctl daemon-reload`;
- enable/restart `roamer-wake.service` only when config has `driver: su03t_gpio` and wakeword enabled;
- fail if GPIO dependency import fails while SU-03T wake is enabled.

- [ ] **Step 3: Document install**

Add README install notes for SU-03T wiring:

```text
SU-03T VCC -> Pi 5V pin 2/4
SU-03T GND -> Pi GND pin 6
SU-03T OUT -> GPIO17 physical pin 11
```

- [ ] **Step 4: Verify**

Run:

```bash
bash -n install.sh
.venv/bin/ruff check install.sh README.md systemd/roamer-wake.service
```

Expected: `bash -n` succeeds. If `ruff` does not accept non-Python files, run ruff only on changed Python files in other tasks.

- [ ] **Step 5: Commit**

```bash
git add systemd/roamer-wake.service install.sh README.md
git commit -m "install: add SU-03T wake service"
```

## Task 8: Roamer Deployment and E2E

**Files:**
- No source change expected unless hardware test reveals a bug.

- [ ] **Step 1: Run full local unit suite**

Run:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check src tests
```

Expected: PASS.

- [ ] **Step 2: Push/pull to Roamer**

Run from local:

```bash
git push origin HEAD
ssh -o HostKeyAlias=roamer richerd@10.0.0.225 'cd /home/richerd/worksp/richerd-roamer && git pull --ff-only && ./install.sh'
```

Expected: install succeeds and `roamer-wake.service` is active if wake is enabled.

- [ ] **Step 3: Manual one-shot wake test**

Run on Roamer:

```bash
roamer wake --once --timeout 30
```

Trigger SU-03T and say `Richard 现在几点了`.

Expected: JSON includes `ok: true`, wake phrase matched, command text `现在几点了`, and a local `time.now` route.

- [ ] **Step 4: Service E2E**

Run:

```bash
sudo systemctl status roamer-wake.service
journalctl -u roamer-wake.service -n 100 --no-pager
```

Expected: service is active, no crash loop, logs show wake loop ready.

- [ ] **Step 5: Commit hardware fixes if any**

If the E2E exposes defects, fix them with targeted tests first, rerun the relevant suite,
and commit with a specific message.

## Task 9: Review, Fix, PR

**Files:**
- Any file from prior tasks if review finds issues.

- [ ] **Step 1: Gemini review**

Run:

```bash
gemini --version
gemini -p "Review this Roamer SU-03T wakeword implementation for functional completeness, bugs, fit with existing code structure, and missing tests. Be specific and actionable." .
```

Expected: Gemini CLI runs and produces findings.

- [ ] **Step 2: Fallback review if Gemini is unavailable**

If Gemini CLI is unavailable, use a reviewer subagent with this prompt:

```text
Review the current Roamer SU-03T wakeword implementation. Standards: feature complete against specs/2026-05-05-su03t-wakeword-design.md and plans/2026-05-06-su03t-wakeword-implementation.md, no obvious bugs, implementation fits existing code structure, tests cover behavior. Return actionable findings only.
```

- [ ] **Step 3: Fix all review findings**

For every finding:

1. Write or update a failing test if the issue is behavioral.
2. Implement the smallest fix.
3. Run the targeted test.
4. Commit the fix.

- [ ] **Step 4: Repeat review**

Repeat Gemini/subagent review until there are no actionable findings.

- [ ] **Step 5: Final verification**

Run:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check src tests
git status --short
```

Expected: tests pass, lint passes, only intentional untracked/ignored files remain.

- [ ] **Step 6: Open PR**

Run:

```bash
git push origin HEAD
gh pr create --fill
```

Expected: PR URL is produced.

## Self-Review Checklist

- Spec coverage: hardware wiring, SU-03T driver, GPIO17, pre-roll, Silero endpointing, ASR phrase confirmation, converse routing, follow-up mode, speaking suppression, systemd, installer, tests, review, and PR are each mapped to tasks.
- Placeholder scan: this plan intentionally contains no TBD/TODO placeholders.
- Type consistency: driver name is `su03t_gpio`; class name is `Su03tGpioDriver`; wake phrase matcher returns `WakeMatch`; wake CLI command is `roamer wake`.

