from __future__ import annotations

from roamerd.kernel import StateManager


class WakeGate:
    def __init__(self, state: StateManager | None = None) -> None:
        self._state = state
        self._playback_active = False

    def playback_started(self) -> None:
        self._playback_active = True

    def playback_finished(self) -> None:
        self._playback_active = False

    def should_ignore_wake(self) -> bool:
        if self._state is not None:
            return self._state.is_speaking
        return self._playback_active
