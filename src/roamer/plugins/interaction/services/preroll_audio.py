"""Pre-roll audio chunk buffering for GPIO-triggered wake."""

from __future__ import annotations

import queue
import threading
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
        self._live_chunks: queue.Queue[bytes] = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start background capture resources.

        The current implementation is iterator-driven; production callers provide an
        already-live chunk source and tests can drain it deterministically.
        """
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop background capture resources."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        self._thread = None

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
        self.clear_live_queue()
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
                chunk = self._next_live_chunk()
            except StopIteration:
                return
            self._buffer.append(chunk)
            yielded += 1
            yield chunk

    def _read_loop(self) -> None:
        for chunk in self._chunk_iter:
            if self._stop.is_set():
                return
            self._buffer.append(chunk)
            self._live_chunks.put(chunk)

    def _next_live_chunk(self) -> bytes:
        if self._thread is None:
            return next(self._chunk_iter)
        try:
            return self._live_chunks.get(timeout=self._chunk_duration_sec * 2)
        except queue.Empty as exc:
            raise StopIteration from exc

    def clear_live_queue(self) -> None:
        """Discard chunks already represented by the pre-roll snapshot."""
        while True:
            try:
                self._live_chunks.get_nowait()
            except queue.Empty:
                return
