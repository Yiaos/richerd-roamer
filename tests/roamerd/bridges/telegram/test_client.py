import pytest

from roamerd.bridges.telegram.client import FakeTelegramClient, TelegramBridge
from roamerd.events import Event
from roamerd.kernel import EventBus


@pytest.mark.asyncio
async def test_telegram_bridge_notifies_on_cognition_unavailable_with_redaction() -> None:
    bus = EventBus()
    client = FakeTelegramClient()
    bridge = TelegramBridge(client=client, enabled=True, log_transcripts=False)
    await bridge.start(bus)

    await bus.publish(
        Event(
            event_type="cognition.unavailable",
            source="test",
            session_id="s",
            payload={"reason": "timeout", "text": "secret words"},
        )
    )
    await bus.run_until_idle()

    assert client.messages == ["cognition unavailable: timeout text=[redacted]"]
