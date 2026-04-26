"""Reminder action wrapper for interaction plugin."""

from typing import Any


class RemindAction:
    """Dispatch reminder scheduling through reminder capability."""

    def __init__(self, config: dict[str, Any]):
        from roamer.plugins.interaction.capabilities.remind import RemindCapability

        self._capability = RemindCapability(config)

    def run(self, delay_sec: float, text: str) -> dict[str, Any]:
        """Schedule one spoken reminder."""
        return self._capability.schedule(delay_sec=delay_sec, text=text)
