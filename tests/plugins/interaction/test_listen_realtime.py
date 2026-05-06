"""Tests for realtime STT integration in listen capability."""

from unittest.mock import Mock, patch

from roamer.plugins.interaction.capabilities.listen import ListenCapability


def _config() -> dict:
    return {
        "drivers": {"vad": "silero", "asr": "funasr", "audio": "alsa"},
        "alsa": {"sample_rate": 16000, "channels": 2},
        "silero": {"threshold": 0.5},
        "funasr": {"model": "paraformer"},
        "converse": {
            "stt": {
                "mode": "realtime_with_batch_fallback",
                "provider": "vllm_realtime",
                "url": "ws://example.test/v1/realtime",
                "model": "qwen3-asr-0.6b",
                "response_timeout_sec": 7.0,
            },
            "endpoint": {
                "mode": "vad_endpoint",
                "chunk_duration_sec": 0.1,
                "max_record_sec": 3.0,
            },
        },
    }


def test_listen_uses_realtime_endpoint_transcriber_when_configured() -> None:
    fake_vad = Mock()
    fake_audio = Mock()
    fake_audio.stream_chunks.return_value = iter([b"\x00\x00"])
    fake_asr = Mock()
    provider = Mock()
    transcriber = Mock()
    transcriber.transcribe.return_value = {
        "ok": True,
        "text": "现在几点了",
        "provider": "vllm_realtime",
    }

    with patch(
        "roamer.plugins.interaction.capabilities.listen.get_driver",
        side_effect=[fake_vad, fake_asr],
    ):
        with patch(
            "roamer.plugins.interaction.capabilities.audio.get_driver",
            return_value=fake_audio,
        ):
            cap = ListenCapability(_config())

    with patch(
        "roamer.plugins.interaction.capabilities.listen.VllmRealtimeSTTProvider",
        return_value=provider,
    ) as provider_cls:
        with patch(
            "roamer.plugins.interaction.capabilities.listen.RealtimeEndpointTranscriber",
            return_value=transcriber,
        ) as transcriber_cls:
            result = cap.listen(timeout=3.0, use_endpointing=True)

    assert result["ok"] is True
    assert result["text"] == "现在几点了"
    provider_cls.assert_called_once()
    transcriber_cls.assert_called_once()
    assert transcriber_cls.call_args.kwargs["provider"] is provider
    assert transcriber_cls.call_args.kwargs["endpoint_config"].chunk_duration_sec == 0.1
    assert transcriber_cls.call_args.kwargs["response_timeout_sec"] == 7.0
    assert callable(transcriber_cls.call_args.kwargs["fallback_transcribe"])


def test_listen_realtime_returns_structured_audio_error_when_stream_creation_fails() -> None:
    fake_vad = Mock()
    fake_audio = Mock()
    fake_audio.stream_chunks.side_effect = FileNotFoundError("arecord")
    fake_asr = Mock()

    with patch(
        "roamer.plugins.interaction.capabilities.listen.get_driver",
        side_effect=[fake_vad, fake_asr],
    ):
        with patch(
            "roamer.plugins.interaction.capabilities.audio.get_driver",
            return_value=fake_audio,
        ):
            cap = ListenCapability(_config())

    result = cap.listen(timeout=3.0, use_endpointing=True)

    assert result["ok"] is False
    assert result["error"] == "audio_record_failed"
    assert result["error_code"] == "dependency.audio.arecord_missing"
