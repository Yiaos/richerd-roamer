"""Adapters for forwarding memory candidates to richerd-memory."""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib import error as url_error
from urllib import request as url_request

from roamerd.events.memory import MemoryCandidatePayload
from roamerd.kernel.state_manager import HealthState

UrlOpen = Callable[..., Any]


class HttpMemoryAdapter:
    def __init__(
        self,
        *,
        endpoint: str,
        timeout_sec: float,
        urlopen: UrlOpen | None = None,
    ) -> None:
        endpoint = endpoint.rstrip("/")
        if not endpoint:
            raise ValueError("endpoint is required")
        self._endpoint = endpoint
        self._timeout_sec = timeout_sec
        self._urlopen = urlopen or url_request.urlopen

    async def submit_candidate(self, candidate: MemoryCandidatePayload) -> bool:
        try:
            data = self._request_json(
                "POST",
                "/memory/candidates",
                candidate.model_dump(mode="json"),
            )
        except Exception:
            return False
        ok = data.get("ok")
        return ok is True or data == {}

    async def health_check(self) -> HealthState:
        try:
            data = self._request_json("GET", "/health")
        except Exception:
            return HealthState.UNAVAILABLE
        if data.get("ok") is True:
            return HealthState.HEALTHY
        status = data.get("status")
        if isinstance(status, str) and status.lower() in {"ok", "healthy", "ready"}:
            return HealthState.HEALTHY
        return HealthState.DEGRADED

    def _request_json(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        data: bytes | None = None
        headers: dict[str, str] = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = url_request.Request(
            url=f"{self._endpoint}{path}", method=method, data=data, headers=headers
        )
        try:
            with self._urlopen(request, timeout=self._timeout_sec) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except url_error.URLError:
            raise
        if not raw.strip():
            return {}
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise RuntimeError("memory service returned non-object JSON")
        return parsed
