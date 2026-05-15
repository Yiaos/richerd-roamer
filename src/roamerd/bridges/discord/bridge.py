"""Discord bridge preserving transport boundaries."""

from __future__ import annotations

import json
from typing import Protocol, runtime_checkable
from uuid import uuid4

from roamerd.events.base import Event, Priority, make_event
from roamerd.events.control import ControlCommandPayload
from roamerd.kernel.event_bus import EventBus
from roamerd.kernel.state_manager import HealthState


@runtime_checkable
class DiscordAdapter(Protocol):
    async def send_message(self, content: str) -> bool: ...

    async def health_check(self) -> HealthState: ...


class DiscordBridge:
    name = "discord"

    def __init__(
        self,
        *,
        session_id: str,
        enabled: bool = False,
        adapter: DiscordAdapter | None = None,
        source: str = "roamer",
        mention: str = "",
        reply_instruction: str = "",
    ) -> None:
        self._session_id = session_id
        self._enabled = enabled
        self._adapter = adapter
        self._source = source
        self._mention = mention.strip()
        self._reply_instruction = reply_instruction.strip()
        self._bus: EventBus | None = None

    async def start(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe("action.started", self._on_action_started)
        bus.subscribe("cognition.unavailable", self._on_cognition_unavailable)
        await bus.publish(
            make_event(
                "system.module_ready",
                source="discord_bridge",
                session_id=self._session_id,
                payload={
                    "name": self.name,
                    "component_type": "bridge",
                    "state": "healthy" if self._enabled else "degraded",
                },
            )
        )

    async def stop(self) -> None:
        return None

    async def health_check(self) -> HealthState:
        if not self._enabled:
            return HealthState.DEGRADED
        if self._adapter is None:
            return HealthState.UNAVAILABLE
        return await self._adapter.health_check()

    async def ingest_message(self, *, message_id: str, author_id: str, content: str) -> bool:
        if not self._enabled or self._bus is None:
            return False
        try:
            raw = json.loads(content)
        except json.JSONDecodeError:
            return False
        if not isinstance(raw, dict):
            return False
        raw.setdefault("correlation_id", uuid4().hex[:12])
        raw.setdefault("request_id", message_id)
        raw["client"] = "discord"
        raw["source"] = "discord"
        raw["actor"] = author_id
        command = ControlCommandPayload.model_validate(raw)
        await self._bus.publish(
            make_event(
                "control.command_received",
                source="discord_bridge",
                session_id=self._session_id,
                payload=command.model_dump(mode="json"),
                correlation_id=command.correlation_id,
                priority=Priority.HIGH,
            )
        )
        return True

    async def _on_action_started(self, event: Event) -> None:
        if not self._enabled or event.payload.get("action_type") != "speak":
            return
        payload = event.payload.get("payload")
        text = payload.get("text") if isinstance(payload, dict) else None
        if isinstance(text, str) and text.strip():
            await self._send(_with_instruction(self._prefix(text.strip()), self._reply_instruction))

    async def _on_cognition_unavailable(self, event: Event) -> None:
        reason = str(event.payload.get("reason", "unknown"))
        await self._send(
            _with_instruction(
                self._prefix(f"cognition unavailable: {reason}"),
                self._reply_instruction,
            )
        )

    async def _send(self, content: str) -> bool:
        if not self._enabled or self._adapter is None:
            return False
        return await self._adapter.send_message(content)

    def _prefix(self, content: str) -> str:
        if not self._mention:
            return content
        return f"{self._mention} {content}"


def _with_instruction(content: str, instruction: str) -> str:
    if not instruction:
        return content
    return f"{content}\n{instruction}"
