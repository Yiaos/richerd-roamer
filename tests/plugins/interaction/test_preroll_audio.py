"""Tests for pre-roll audio chunk buffering."""

import time

from roamer.plugins.interaction.services.preroll_audio import PreRollAudioSource


def test_preroll_snapshot_keeps_recent_chunks() -> None:
    source = PreRollAudioSource(
        chunk_source=iter([b"a", b"b", b"c"]),
        chunk_duration_sec=0.5,
        pre_roll_sec=1.0,
    )

    source.drain_available_for_test()

    assert source.snapshot() == [b"b", b"c"]


def test_capture_iter_yields_snapshot_then_live_chunks() -> None:
    source = PreRollAudioSource(
        chunk_source=iter([b"a", b"b", b"c", b"d"]),
        chunk_duration_sec=0.5,
        pre_roll_sec=1.0,
    )
    source.drain_available_for_test(limit=2)

    assert list(source.capture_iter(max_duration_sec=1.0)) == [b"a", b"b", b"c", b"d"]


def test_capture_iter_waits_for_delayed_live_chunks() -> None:
    def delayed_chunks():
        yield b"a"
        time.sleep(0.15)
        yield b"b"

    source = PreRollAudioSource(
        chunk_source=delayed_chunks(),
        chunk_duration_sec=0.01,
        pre_roll_sec=0.1,
    )
    source.start()
    try:
        chunks = list(source.capture_iter(max_duration_sec=0.5))
    finally:
        source.stop()

    assert chunks == [b"a", b"b"]


def test_capture_iter_does_not_drop_live_chunks_when_consumer_lags() -> None:
    chunks = [f"c{i}".encode() for i in range(8)]

    def delayed_chunks():
        time.sleep(0.02)
        yield from chunks

    source = PreRollAudioSource(
        chunk_source=delayed_chunks(),
        chunk_duration_sec=0.01,
        pre_roll_sec=0.02,
    )
    source.start()
    try:
        captured = []
        iterator = source.capture_iter(max_duration_sec=1.0)
        captured.append(next(iterator))
        time.sleep(0.05)
        captured.extend(iterator)
    finally:
        source.stop()

    assert captured == chunks


def test_clear_removes_buffered_and_live_chunks() -> None:
    source = PreRollAudioSource(
        chunk_source=iter([b"a", b"b"]),
        chunk_duration_sec=0.5,
        pre_roll_sec=1.0,
    )
    source.drain_available_for_test()

    source.clear()

    assert source.snapshot() == []


def test_live_queue_is_bounded_while_idle() -> None:
    source = PreRollAudioSource(
        chunk_source=iter([b"a", b"b", b"c", b"d", b"e"]),
        chunk_duration_sec=0.5,
        pre_roll_sec=1.0,
    )

    source.start()
    deadline = time.monotonic() + 1.0
    while source.running and time.monotonic() < deadline:
        time.sleep(0.001)

    assert source._live_chunks.qsize() <= 2


def test_exhausted_source_reports_not_running_after_reader_stops() -> None:
    source = PreRollAudioSource(
        chunk_source=iter([b"a"]),
        chunk_duration_sec=0.01,
        pre_roll_sec=1.0,
    )
    source.start()
    source.stop()

    assert source.running is False


def test_reader_error_is_exposed_after_background_failure() -> None:
    def chunks():
        yield b"a"
        raise OSError("usb audio disconnected")

    source = PreRollAudioSource(
        chunk_source=chunks(),
        chunk_duration_sec=0.01,
        pre_roll_sec=0.1,
    )
    source.start()
    deadline = time.monotonic() + 1.0
    while source.running and time.monotonic() < deadline:
        time.sleep(0.001)

    assert source.running is False
    assert isinstance(source.reader_error, OSError)
    assert source.healthy is False


def test_stop_closes_underlying_chunk_generator() -> None:
    closed = False

    def chunks():
        nonlocal closed
        try:
            yield b"a"
            yield b"b"
        finally:
            closed = True

    source = PreRollAudioSource(
        chunk_source=chunks(),
        chunk_duration_sec=0.5,
        pre_roll_sec=1.0,
    )
    source.drain_available_for_test(limit=1)

    source.stop()

    assert closed is True


def test_stop_ignores_generator_already_executing_close_error() -> None:
    class BusyIterator:
        def __iter__(self):
            return self

        def __next__(self) -> bytes:
            raise StopIteration

        def close(self) -> None:
            raise ValueError("generator already executing")

    source = PreRollAudioSource(
        chunk_source=BusyIterator(),
        chunk_duration_sec=0.5,
        pre_roll_sec=1.0,
    )

    source.stop()

    assert source.running is False
