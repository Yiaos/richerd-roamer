"""Spoken reminder scheduling capability."""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Any

from roamer.platform.output import error, success
from roamer.plugins.interaction.capabilities.base import Capability


class RemindCapability(Capability):
    """Schedule a one-shot spoken reminder owned by Roamer."""

    def schedule(self, *, delay_sec: float, text: str) -> dict[str, Any]:
        """Schedule a reminder by spawning a detached local process."""
        message = text.strip()
        if delay_sec <= 0:
            return error("config_invalid", "delay_sec must be greater than 0")
        if not message:
            return error("config_invalid", "reminder text must not be empty")

        due_at = datetime.now().astimezone() + timedelta(seconds=delay_sec)
        script = (
            "import subprocess, time\n"
            f"time.sleep({float(delay_sec)!r})\n"
            f"subprocess.run(['roamer', 'speak', {('提醒：' + message)!r}], check=False)\n"
        )
        proc = subprocess.Popen(  # noqa: S603 - local roamer CLI invocation, no shell.
            [sys.executable, "-c", script],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return success(
            scheduled=True,
            delay_sec=float(delay_sec),
            due_at=due_at.isoformat(),
            text=message,
            pid=proc.pid,
        )


def parse_delay(value: str) -> float:
    """Parse human-friendly duration strings into seconds."""
    text = value.strip().lower()
    duration_re = (
        r"(\d+(?:\.\d+)?)(?:\s*)"
        r"(s|sec|secs|second|seconds|秒|m|min|mins|minute|minutes|分钟|h|hr|hour|hours|小时)?"
    )
    match = re.fullmatch(duration_re, text)
    if not match:
        raise ValueError(f"invalid reminder delay: {value}")
    amount = float(match.group(1))
    unit = match.group(2) or "s"
    if unit in {"m", "min", "mins", "minute", "minutes", "分钟"}:
        return amount * 60
    if unit in {"h", "hr", "hour", "hours", "小时"}:
        return amount * 3600
    return amount
