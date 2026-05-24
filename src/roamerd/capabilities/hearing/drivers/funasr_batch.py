from __future__ import annotations

from typing import Protocol

from roamerd.capabilities.hearing.drivers.network_asr import normalize_asr_text


class FunAsrModel(Protocol):
    def generate(self, pcm: bytes) -> str: ...


class FunAsrBatchDriver:
    def __init__(self, model: FunAsrModel) -> None:
        self._model = model

    async def transcribe(self, pcm: bytes) -> str:
        return normalize_asr_text(self._model.generate(pcm))
