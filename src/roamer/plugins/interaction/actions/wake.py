"""Wake action wrapper for SU-03T hands-free mode."""

from typing import Any


class WakeAction:
    """Dispatch wake loop calls through wake capability."""

    def __init__(self, config: dict[str, Any]):
        from roamer.plugins.interaction.capabilities.wake import WakeCapability

        self._capability = WakeCapability(config)

    def run(
        self,
        *,
        once: bool = False,
        timeout: float | None = None,
        no_sound: bool = False,
    ) -> dict[str, Any]:
        return self._capability.run(once=once, timeout=timeout, no_sound=no_sound)
