"""Discord REST API adapter."""

from __future__ import annotations

import json
import os
from typing import Any, Callable
from urllib import error as url_error
from urllib import request as url_request

from roamerd.kernel.state_manager import HealthState

UrlOpen = Callable[..., Any]


class HttpDiscordAdapter:
    def __init__(
        self,
        *,
        channel_id: str,
        token_env: str,
        timeout_sec: float = 3.0,
        urlopen: UrlOpen | None = None,
    ) -> None:
        self._channel_id = channel_id.strip()
        self._token_env = token_env
        self._timeout_sec = timeout_sec
        self._urlopen = urlopen or url_request.urlopen

    async def send_message(self, content: str) -> bool:
        token = os.getenv(self._token_env, "")
        if not self._channel_id or not token:
            return False
        request = url_request.Request(
            url=f"https://discord.com/api/v10/channels/{self._channel_id}/messages",
            method="POST",
            data=json.dumps({"content": content}).encode("utf-8"),
            headers={
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json",
                "User-Agent": "roamerd/1.0",
            },
        )
        try:
            with self._urlopen(request, timeout=self._timeout_sec) as response:
                status = int(getattr(response, "status", response.getcode()))
        except (url_error.URLError, OSError):
            return False
        return 200 <= status < 300

    async def health_check(self) -> HealthState:
        if not self._channel_id or not os.getenv(self._token_env, ""):
            return HealthState.UNAVAILABLE
        return HealthState.HEALTHY
