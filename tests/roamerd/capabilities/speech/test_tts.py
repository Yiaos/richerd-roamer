from pathlib import Path

import pytest

from roamerd.capabilities.speech.drivers.edge_tts import EdgeTtsDriver
from roamerd.capabilities.speech.drivers.fallback import FallbackTtsDriver
from roamerd.capabilities.speech.drivers.piper import PiperTtsDriver
from roamerd.capabilities.speech.drivers.tts_base import SynthResult


@pytest.mark.asyncio
async def test_edge_tts_driver_invokes_cli(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    async def runner(command: list[str], timeout_sec: float) -> None:
        calls.append(command)
        assert timeout_sec == 20.0
        Path(command[-1]).write_bytes(b"wav")

    output = tmp_path / "out.wav"
    driver = EdgeTtsDriver(voice="zh-CN-YunxiNeural", command_runner=runner)

    result = await driver.synthesize("你好", output)

    assert result == SynthResult(path=output, duration_ms=None)
    assert calls == [
        ["edge-tts", "--voice", "zh-CN-YunxiNeural", "--text", "你好", "--write-media", str(output)]
    ]


@pytest.mark.asyncio
async def test_piper_driver_invokes_binary(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    async def runner(command: list[str], input_text: str, timeout_sec: float) -> None:
        calls.append(command)
        assert input_text == "你好"
        assert timeout_sec == 20.0
        Path(command[-1]).write_bytes(b"wav")

    output = tmp_path / "out.wav"
    driver = PiperTtsDriver(binary="piper", model="voice.onnx", command_runner=runner)

    assert await driver.synthesize("你好", output) == SynthResult(path=output, duration_ms=None)
    assert calls == [["piper", "--model", "voice.onnx", "--output_file", str(output)]]


@pytest.mark.asyncio
async def test_fallback_tts_uses_secondary_when_primary_fails(tmp_path: Path) -> None:
    class FailingTts:
        async def synthesize(self, text: str, output_path: Path) -> SynthResult:
            raise RuntimeError("edge unavailable")

    class WorkingTts:
        async def synthesize(self, text: str, output_path: Path) -> SynthResult:
            return SynthResult(path=output_path, duration_ms=1)

    result = await FallbackTtsDriver(FailingTts(), WorkingTts()).synthesize(
        "你好", tmp_path / "out.wav"
    )

    assert result.duration_ms == 1
