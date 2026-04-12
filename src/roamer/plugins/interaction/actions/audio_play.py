"""Audio play action wrapper for interaction plugin."""

from typing import Any


class AudioPlayAction:
    """Dispatch audio playback through audio capability."""

    def __init__(self, config: dict[str, Any]):
        from roamer.plugins.interaction.capabilities.audio import AudioCapability

        self._capability = AudioCapability(config)

    def run(self, file: str) -> dict[str, Any]:
        """Run audio playback."""
        return self._capability.play(file)
