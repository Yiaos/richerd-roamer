"""Audio record action wrapper for interaction plugin."""

from typing import Any


class AudioRecordAction:
    """Dispatch audio recording through audio capability."""

    def __init__(self, config: dict[str, Any]):
        from roamer.plugins.interaction.capabilities.audio import AudioCapability

        self._capability = AudioCapability(config)

    def run(self, duration: float = 5.0, output: str | None = None) -> dict[str, Any]:
        """Run audio recording."""
        return self._capability.record(duration=duration, output=output)
