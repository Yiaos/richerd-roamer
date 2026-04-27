"""Converse action wrapper for interaction plugin."""

from typing import Any


class ConverseAction:
    """Dispatch converse calls through converse capability."""

    def __init__(self, config: dict[str, Any]):
        from roamer.plugins.interaction.capabilities.converse import ConverseCapability

        self._capability = ConverseCapability(config)

    def run(
        self,
        no_wakeword: bool = False,
        timeout: float = 8.0,
        no_sound: bool = False,
        max_turns: int = 10,
        use_endpointing: bool = False,
    ) -> dict[str, Any]:
        return self._capability.run(
            no_wakeword=no_wakeword,
            timeout=timeout,
            no_sound=no_sound,
            max_turns=max_turns,
            use_endpointing=use_endpointing,
        )
