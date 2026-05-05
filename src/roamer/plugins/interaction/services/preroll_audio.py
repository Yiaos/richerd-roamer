"""Pre-roll audio chunk buffering for GPIO-triggered wake."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Iterator


class PreRollAudioSource:
    """Keep recent audio chunks and replay them before live capture chunks."""

    def __init__(
        self,
        *,
        chunk_source: Iterable[bytes],
        chunk_duration_sec: float,
        pre_roll_sec: float,
    ):
        self._chunk_iter = iter(chunk_source)
        self._chunk_duration_sec = float(chunk_duration_sec)
        self._pre_roll_sec = float(pre_roll_sec)
        maxlen = max(1, int(round(self._pre_roll_sec / self._chunk_duration_sec)))
        self._buffer: deque[bytes] = deque(maxlen=maxlen)

    def start(self) -> None:
        """Start background capture resources.

        The current implementation is iterator-driven; production callers provide an
        already-live chunk source and tests can drain it deterministically.
        """

    def stop(self) -> None:
        """Stop background capture resources."""

    def snapshot(self) -> list[bytes]:
        """Return buffered pre-roll chunks in playback order."""
        return list(self._buffer)

    def drain_available_for_test(self, limit: int | None = None) -> None:
        """Drain chunks into the pre-roll buffer for deterministic unit tests."""
        count = 0
        while limit is None or count < limit:
            try:
                chunk = next(self._chunk_iter)
            except StopIteration:
                return
            self._buffer.append(chunk)
            count += 1

    def capture_iter(self, max_duration_sec: float) -> Iterator[bytes]:
        """Yield current pre-roll snapshot followed by live chunks."""
        snapshot = self.snapshot()
        yield from self.chunks_after_snapshot(snapshot, max_duration_sec=max_duration_sec)

    def chunks_after_snapshot(
        self,
        snapshot: list[bytes],
        *,
        max_duration_sec: float,
    ) -> Iterator[bytes]:
        """Yield snapshot chunks and then consume live chunks up to max duration."""
        max_chunks = max(1, int(round(float(max_duration_sec) / self._chunk_duration_sec)))
        for chunk in snapshot:
            yield chunk
        yielded = 0
        while yielded < max_chunks:
            try:
                chunk = next(self._chunk_iter)
            except StopIteration:
                return
            self._buffer.append(chunk)
            yielded += 1
            yield chunk
