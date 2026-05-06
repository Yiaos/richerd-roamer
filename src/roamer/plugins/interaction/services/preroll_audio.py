"""Pre-roll audio chunk buffering for GPIO-triggered wake."""

from __future__ import annotations

import queue
import threading
import time
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
        self._live_chunks: queue.Queue[bytes] = queue.Queue(maxsize=maxlen)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        """Start background capture resources.

        The current implementation is iterator-driven; production callers provide an
        already-live chunk source and tests can drain it deterministically.
        """
        if self._thread is not None:
            return
        self._stop.clear()
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop background capture resources."""
        self._stop.set()
        self._close_chunk_iter()
        if self._thread is not None:
            self._thread.join(timeout=1)
        self._thread = None
        self._close_chunk_iter()
        self._running = False

    @property
    def running(self) -> bool:
        """Whether the background reader is expected to be alive."""
        return bool(self._running and self._thread is not None and self._thread.is_alive())

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
        deadline = time.monotonic() + float(max_duration_sec)
        while yielded < max_chunks and time.monotonic() < deadline:
            try:
                wait_timeout = min(0.25, max(0.0, deadline - time.monotonic()))
                chunk = self._next_live_chunk(timeout=wait_timeout)
            except TimeoutError:
                continue
            except StopIteration:
                return
            self._buffer.append(chunk)
            yielded += 1
            yield chunk

    def _read_loop(self) -> None:
        try:
            for chunk in self._chunk_iter:
                if self._stop.is_set():
                    return
                self._buffer.append(chunk)
                self._put_live_chunk(chunk)
        finally:
            self._running = False

    def _next_live_chunk(self, timeout: float | None = None) -> bytes:
        if self._thread is None:
            return next(self._chunk_iter)
        wait_sec = timeout if timeout is not None else max(0.25, self._chunk_duration_sec * 4)
        try:
            return self._live_chunks.get(timeout=wait_sec)
        except queue.Empty as exc:
            if self.running:
                raise TimeoutError from exc
            raise StopIteration from exc

    def _put_live_chunk(self, chunk: bytes) -> None:
        while self._live_chunks.full():
            try:
                self._live_chunks.get_nowait()
            except queue.Empty:
                break
        self._live_chunks.put_nowait(chunk)

    def _close_chunk_iter(self) -> None:
        close = getattr(self._chunk_iter, "close", None)
        if close is None:
            return
        try:
            close()
        except (RuntimeError, ValueError):
            return

    def clear_live_queue(self) -> None:
        """Discard chunks already represented by the pre-roll snapshot."""
        while True:
            try:
                self._live_chunks.get_nowait()
            except queue.Empty:
                return

    def clear(self) -> None:
        """Discard pre-roll and queued live chunks."""
        self._buffer.clear()
        self.clear_live_queue()
