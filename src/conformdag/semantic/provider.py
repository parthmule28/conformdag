"""OpenAI-compatible semantic provider transport and typed failures."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from time import monotonic, sleep
from typing import Any, cast

import httpx

from conformdag.models import SemanticRequest, SemanticResponse


class SemanticProviderError(RuntimeError):
    """Raised for unavailable providers or invalid structured responses."""


def strict_semantic_response_schema() -> dict[str, Any]:
    """Return the canonical response schema adapted for strict JSON-schema providers."""
    schema = deepcopy(SemanticResponse.model_json_schema())
    provider_fields = (
        "status",
        "evidence",
        "explanation",
        "remediation",
        "confidence",
        "audit_evidence",
    )
    root_properties = cast(dict[str, Any], schema["properties"])
    schema["properties"] = {name: root_properties[name] for name in provider_fields}

    def close_objects(value: Any) -> None:
        if isinstance(value, dict):
            mapping = cast(dict[str, Any], value)
            mapping.pop("default", None)
            properties = mapping.get("properties")
            if mapping.get("type") == "object" and isinstance(properties, dict):
                property_map = cast(dict[str, Any], properties)
                mapping["required"] = list(property_map)
                mapping["additionalProperties"] = False
            for child in mapping.values():
                close_objects(child)
        elif isinstance(value, list):
            for child in cast(list[Any], value):
                close_objects(child)

    close_objects(schema)
    schema["required"] = list(provider_fields)
    return schema


class OpenAICompatibleProvider:
    """Call an OpenAI-compatible chat endpoint with bounded retries and no tools."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        native_structured_output: bool = False,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.native_structured_output = native_structured_output
        self._client = client

    def evaluate(self, request: SemanticRequest) -> SemanticResponse:
        started = monotonic()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {
                    "role": "user",
                    "content": "<untrusted-evidence>\n" + request.evidence + "\n</untrusted-evidence>",
                },
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
        }
        if self.native_structured_output:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "conformdag_semantic_response",
                    "strict": True,
                    "schema": strict_semantic_response_schema(),
                },
            }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        attempts = 0
        while True:
            try:
                response = self._request(payload, headers)
            except httpx.TransportError as exc:
                if attempts >= self.max_retries:
                    raise SemanticProviderError(f"provider transport failed: {exc}") from exc
                attempts += 1
                sleep(0.1 * attempts)
                continue
            if response.status_code in {408, 429} or response.status_code >= 500:
                if attempts >= self.max_retries:
                    raise SemanticProviderError(f"provider returned HTTP {response.status_code}")
                attempts += 1
                sleep(0.1 * attempts)
                continue
            if response.status_code >= 400:
                raise SemanticProviderError(f"provider returned HTTP {response.status_code}")
            try:
                body = response.json()
                content = body["choices"][0]["message"]["content"]
                result = SemanticResponse.model_validate(json.loads(content))
                served_model = body.get("model")
                if served_model is not None and served_model != self.model:
                    raise SemanticProviderError(f"provider served model {served_model!r}, requested {self.model!r}")
                raw_usage = body.get("usage", {})
                usage = {
                    str(key): int(value) for key, value in raw_usage.items() if isinstance(value, int) and value >= 0
                }
                return result.model_copy(
                    update={
                        "served_model": served_model,
                        "usage": usage,
                        "retries": attempts,
                        "latency_ms": max(0, round((monotonic() - started) * 1000)),
                        "cache_hit": False,
                        "repeatability": "not-measured",
                        "pricing_provenance": None,
                    }
                )
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise SemanticProviderError(f"invalid structured provider response: {exc}") from exc

    def evaluate_many(
        self,
        requests: Sequence[SemanticRequest],
        max_concurrency: int = 4,
    ) -> list[SemanticResponse]:
        """Evaluate requests concurrently while preserving their input order."""
        if max_concurrency < 1 or max_concurrency > 4:
            raise ValueError("semantic concurrency must be between 1 and 4")
        with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
            return list(executor.map(self.evaluate, requests))

    def _request(self, payload: Mapping[str, object], headers: Mapping[str, str]) -> httpx.Response:
        if self._client is not None:
            return self._client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        with httpx.Client(timeout=self.timeout_seconds) as client:
            return client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
