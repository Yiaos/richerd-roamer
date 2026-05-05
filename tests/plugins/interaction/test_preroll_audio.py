"""Tests for pre-roll audio chunk buffering."""

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
