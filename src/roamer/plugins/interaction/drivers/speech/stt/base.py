"""Base interface for realtime STT providers."""

from abc import ABC, abstractmethod
from typing import Any


class RealtimeSTTProvider(ABC):
    """Synchronous realtime STT provider boundary."""

    @abstractmethod
    def start(self) -> None:
        """Open the provider session and prepare to accept PCM chunks."""
        raise NotImplementedError

    @abstractmethod
    def append_pcm16(self, chunk: bytes) -> None:
        """Append one mono PCM16 chunk to the active session."""
        raise NotImplementedError

    @abstractmethod
    def finish(self, timeout_sec: float) -> dict[str, Any]:
        """Finalize the current utterance and return the transcript result."""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Close provider resources."""
        raise NotImplementedError
