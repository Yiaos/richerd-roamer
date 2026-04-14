"""Speak action wrapper for interaction plugin."""

from typing import Any


class SpeakAction:
    """Dispatch speak calls through speak capability."""

    def __init__(self, config: dict[str, Any]):
        from roamer.plugins.interaction.capabilities.speak import SpeakCapability

        self._capability = SpeakCapability(config)

    def run(
        self,
        text: str,
        save_path: str | None = None,
        play: bool = True,
        style: str | None = None,
    ) -> dict[str, Any]:
        """Run text-to-speech flow."""
        return self._capability.speak(text, save_path=save_path, play=play, style=style)
