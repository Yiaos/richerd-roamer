"""Listen action wrapper for interaction plugin."""

from typing import Any


class ListenAction:
    """Dispatch listen calls through listen capability."""

    def __init__(self, config: dict[str, Any]):
        from roamer.plugins.interaction.capabilities.listen import ListenCapability

        self._capability = ListenCapability(config)

    def run(
        self,
        timeout: float = 10.0,
        save_audio: str | None = None,
        debug: bool = False,
    ) -> dict[str, Any]:
        """Run speech listening and transcription."""
        return self._capability.listen(timeout=timeout, save_audio=save_audio, debug=debug)
