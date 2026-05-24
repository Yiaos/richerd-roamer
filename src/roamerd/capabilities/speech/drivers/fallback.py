from __future__ import annotations

from pathlib import Path

from roamerd.capabilities.speech.drivers.tts_base import SynthResult, TtsDriver


class FallbackTtsDriver:
    def __init__(self, primary: TtsDriver, secondary: TtsDriver) -> None:
        self._primary = primary
        self._secondary = secondary

    async def synthesize(self, text: str, output_path: Path) -> SynthResult:
        try:
            return await self._primary.synthesize(text, output_path)
        except Exception:
            return await self._secondary.synthesize(text, output_path)
