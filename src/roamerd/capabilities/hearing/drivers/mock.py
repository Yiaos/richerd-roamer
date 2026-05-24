from __future__ import annotations

import asyncio

from roamerd.capabilities.hearing.drivers.wakeword_base import WakeEvent


class MockWakewordDriver:
    async def wait_for_wake(self) -> WakeEvent:
        await asyncio.Event().wait()
        raise asyncio.CancelledError


class MockAudioCaptureDriver:
    async def record(self) -> bytes:
        return b"mock-pcm"


class MockVadDriver:
    async def is_speech(self, pcm: bytes) -> bool:
        return bool(pcm)


class MockRealtimeSttDriver:
    async def transcribe(self, pcm: bytes) -> str:
        return "现在几点"


class MockBatchAsrDriver:
    async def transcribe(self, pcm: bytes) -> str:
        return "现在几点"
