import pytest

from roamerd.capabilities.hearing.drivers.funasr_batch import FunAsrBatchDriver


class FakeFunAsrModel:
    def generate(self, pcm: bytes) -> str:
        assert pcm == b"pcm"
        return "批处理 文本"


@pytest.mark.asyncio
async def test_funasr_batch_driver_normalizes_model_text() -> None:
    driver = FunAsrBatchDriver(FakeFunAsrModel())

    assert await driver.transcribe(b"pcm") == "批处理文本"
