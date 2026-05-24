from pathlib import Path

from roamerd.capabilities.hearing.endpointing import EndpointConfig, EndpointDetector, save_wav


def test_endpoint_detector_emits_after_silence() -> None:
    detector = EndpointDetector(
        EndpointConfig(
            chunk_ms=100,
            min_duration_ms=200,
            silence_ms=200,
            max_duration_ms=2000,
            pre_padding_ms=100,
        )
    )

    assert detector.add_chunk(b"a", is_speech=False) is None
    assert detector.add_chunk(b"b", is_speech=True) is None
    assert detector.add_chunk(b"c", is_speech=True) is None
    assert detector.add_chunk(b"d", is_speech=False) is None

    assert detector.add_chunk(b"e", is_speech=False) == b"abcde"


def test_endpoint_detector_emits_at_max_duration() -> None:
    detector = EndpointDetector(
        EndpointConfig(chunk_ms=100, min_duration_ms=100, silence_ms=500, max_duration_ms=300)
    )

    assert detector.add_chunk(b"a", is_speech=True) is None
    assert detector.add_chunk(b"b", is_speech=True) is None
    assert detector.add_chunk(b"c", is_speech=True) == b"abc"


def test_save_wav_writes_pcm(tmp_path: Path) -> None:
    path = tmp_path / "out.wav"

    save_wav(path, b"pcm", sample_rate=16000, channels=1)

    assert path.read_bytes().startswith(b"RIFF")
