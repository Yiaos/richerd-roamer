from __future__ import annotations

from typing import Protocol

from roamerd.events import Event
from roamerd.kernel import EventBus


class TelegramClient(Protocol):
    async def send_message(self, text: str) -> None: ...


class FakeTelegramClient:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send_message(self, text: str) -> None:
        self.messages.append(text)


class TelegramBridge:
    name = "telegram"

    def __init__(
        self,
        *,
        client: TelegramClient,
        enabled: bool = False,
        log_transcripts: bool = True,
    ) -> None:
        self._client = client
        self._enabled = enabled
        self._log_transcripts = log_transcripts

    async def start(self, bus: EventBus) -> None:
        bus.subscribe("cognition.unavailable", self._handle_unavailable)

    async def stop(self) -> None:
        return None

    async def health_check(self) -> str:
        return "healthy"

    async def _handle_unavailable(self, event: Event) -> None:
        if not self._enabled:
            return
        reason = str(event.payload.get("reason", "unknown"))
        text = str(event.payload.get("text", ""))
        transcript = text if self._log_transcripts else "[redacted]"
        await self._client.send_message(
            f"cognition unavailable: {reason} text={transcript}"
        )
