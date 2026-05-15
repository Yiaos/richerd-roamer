"""Configured cognition adapters.

Adapters translate between roamerd's internal cognition event payloads and
external cognition services. They do not assemble context or execute actions.
"""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any, Callable
from urllib import error as url_error
from urllib import request as url_request

from roamerd.bridges.cognition.bridge import CognitionAdapter, MockCognitionAdapter
from roamerd.events.cognition import CognitionResponsePayload, CognitionResponseType
from roamerd.kernel.state_manager import HealthState

UrlOpen = Callable[..., Any]


class HttpCognitionAdapter:
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

    async def request(
        self, text: str, *, turn_id: str, correlation_id: str
    ) -> CognitionResponsePayload:
        started_at = perf_counter()
        data = self._request_json(
            "POST",
            "/cognition",
            {"text": text, "turn_id": turn_id, "correlation_id": correlation_id},
        )
        response = _normalize_response(data, correlation_id=correlation_id)
        if response.latency_ms is None:
            response.latency_ms = int((perf_counter() - started_at) * 1000)
        return response

    async def health_check(self) -> HealthState:
        try:
            data = self._request_json("GET", "/health")
        except Exception:
            return HealthState.UNAVAILABLE
        if _health_is_healthy(data):
            return HealthState.HEALTHY
        return HealthState.DEGRADED

    def _request_json(
        self, method: str, path: str, payload: dict[str, object] | None = None
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
        except url_error.URLError as exc:
            raise RuntimeError(f"cognition service unavailable: {exc.reason}") from exc
        if not raw.strip():
            return {}
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise RuntimeError("cognition service returned non-object JSON")
        return parsed


class FallbackCognitionAdapter:
    def __init__(self, *, primary: CognitionAdapter, fallback: CognitionAdapter) -> None:
        self._primary = primary
        self._fallback = fallback

    async def request(
        self, text: str, *, turn_id: str, correlation_id: str
    ) -> CognitionResponsePayload:
        try:
            return await self._primary.request(text, turn_id=turn_id, correlation_id=correlation_id)
        except Exception:
            return await self._fallback.request(
                text, turn_id=turn_id, correlation_id=correlation_id
            )

    async def health_check(self) -> HealthState:
        primary_health = await self._primary.health_check()
        if primary_health == HealthState.HEALTHY:
            return HealthState.HEALTHY
        fallback_health = await self._fallback.health_check()
        if fallback_health == HealthState.HEALTHY:
            return HealthState.DEGRADED
        return HealthState.UNAVAILABLE


def build_cognition_adapter(
    *,
    driver: str,
    endpoint: str,
    timeout_sec: float,
    fallback: str | None = None,
    local_endpoint: str | None = None,
) -> CognitionAdapter:
    primary = _adapter_for(driver=driver, endpoint=endpoint, timeout_sec=timeout_sec)
    if fallback is None:
        return primary
    fallback_endpoint = local_endpoint or endpoint
    return FallbackCognitionAdapter(
        primary=primary,
        fallback=_adapter_for(
            driver=fallback,
            endpoint=fallback_endpoint,
            timeout_sec=timeout_sec,
        ),
    )


def _adapter_for(*, driver: str, endpoint: str, timeout_sec: float) -> CognitionAdapter:
    if driver == "mock":
        return MockCognitionAdapter()
    if driver in {"openclaw", "local_llm"}:
        return HttpCognitionAdapter(endpoint=endpoint, timeout_sec=timeout_sec)
    raise ValueError(f"unsupported cognition driver: {driver}")


def _normalize_response(data: dict[str, Any], *, correlation_id: str) -> CognitionResponsePayload:
    if "choices" in data:
        content = _extract_openai_content(data)
        return CognitionResponsePayload(
            correlation_id=correlation_id,
            response_type=CognitionResponseType.SPEAK,
            text=content,
        )
    action_request = data.get("action_request", data.get("action_intent"))
    text = data.get("text", data.get("message"))
    response_type = data.get("response_type")
    if response_type is None:
        response_type = (
            CognitionResponseType.SPEAK_AND_ACTION.value
            if isinstance(action_request, dict) and text
            else CognitionResponseType.ACTION.value
            if isinstance(action_request, dict)
            else CognitionResponseType.SPEAK.value
        )
    payload: dict[str, Any] = {
        "correlation_id": str(data.get("correlation_id", correlation_id)),
        "response_type": response_type,
        "text": str(text) if text is not None else None,
        "latency_ms": data.get("latency_ms"),
    }
    if isinstance(action_request, dict):
        payload["action_request"] = action_request
    return CognitionResponsePayload.model_validate(payload)


def _extract_openai_content(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return str(content) if content is not None else ""


def _health_is_healthy(data: dict[str, Any]) -> bool:
    if data.get("ok") is True:
        return True
    status = data.get("status")
    return isinstance(status, str) and status.lower() in {"ok", "healthy", "ready"}
