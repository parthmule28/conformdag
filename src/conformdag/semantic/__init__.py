"""Privacy-preserving semantic provider, context, and normalized cache primitives."""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import re
import tempfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, suppress
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from time import monotonic, sleep
from typing import Any, cast

import httpx

from conformdag.models import SemanticRequest, SemanticResponse
from conformdag.security.redaction import CREDENTIAL_PATTERNS, redact_credentials
from conformdag.semantic.context import DEFAULT_SECRET_PATTERNS, SemanticContext, build_context, redact_text
from conformdag.semantic.prompts import DEFAULT_PROMPT_TEMPLATE, GENERIC_REVIEWER_PROMPT, PromptTemplate

LOGGER = logging.getLogger(__name__)

__all__ = [
    "annotations",
    "fcntl",
    "hashlib",
    "json",
    "logging",
    "os",
    "re",
    "tempfile",
    "Iterable",
    "Iterator",
    "Mapping",
    "Sequence",
    "ThreadPoolExecutor",
    "contextmanager",
    "suppress",
    "deepcopy",
    "dataclass",
    "Path",
    "monotonic",
    "sleep",
    "Any",
    "cast",
    "httpx",
    "SemanticRequest",
    "SemanticResponse",
    "CREDENTIAL_PATTERNS",
    "redact_credentials",
    "LOGGER",
    "SemanticProviderError",
    "strict_semantic_response_schema",
    "DEFAULT_SECRET_PATTERNS",
    "SemanticContext",
    "PromptTemplate",
    "DEFAULT_PROMPT_TEMPLATE",
    "GENERIC_REVIEWER_PROMPT",
    "redact_text",
    "build_context",
    "OpenAICompatibleProvider",
    "semantic_cache_key",
    "SemanticCache",
    "CachedSemanticProvider",
]


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


def semantic_cache_key(
    request: SemanticRequest,
    model: str,
    configuration: Mapping[str, object],
) -> str:
    """Hash normalized semantic inputs without retaining raw model I/O."""
    payload = {
        "schema_version": request.schema_version,
        "policy_id": request.policy_id,
        "policy_version": request.policy_version,
        "policy_contract_hash": request.policy_contract_hash,
        "enforcement_hash": request.enforcement_hash,
        "prompt_version": request.prompt_version,
        "response_schema_hash": hashlib.sha256(
            json.dumps(strict_semantic_response_schema(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "context_hash": request.context_hash,
        "model": model,
        "configuration": dict(sorted(configuration.items())),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


class SemanticCache:
    """Filesystem cache containing only schema-validated normalized responses."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @property
    def lock_path(self) -> Path:
        return self.path.with_name(self.path.name + ".lock")

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _load_unlocked(self) -> dict[str, object]:
        if not self.path.is_file():
            return {}
        try:
            loaded: Any = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            return {}
        return cast(dict[str, object], loaded) if isinstance(loaded, dict) else {}

    def get(self, key: str) -> SemanticResponse | None:
        try:
            with self._locked():
                value = self._load_unlocked().get(key)
                return SemanticResponse.model_validate(value).model_copy(update={"cache_hit": True}) if value else None
        except (OSError, TypeError, ValueError):
            return None

    def put(self, key: str, response: SemanticResponse) -> bool:
        """Persist a normalized response without making persistence a scan prerequisite."""
        sanitized = response.model_copy(
            update={
                "evidence": redact_text(response.evidence),
                "explanation": redact_text(response.explanation),
                "remediation": (redact_text(response.remediation) if response.remediation is not None else None),
                "audit_evidence": [
                    item.model_copy(update={"excerpt": redact_text(item.excerpt)}) for item in response.audit_evidence
                ],
            }
        )
        temporary_path: Path | None = None
        try:
            with self._locked():
                payload = self._load_unlocked()
                payload[key] = sanitized.model_dump(mode="json")
                encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.path.parent,
                    prefix=f".{self.path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as stream:
                    temporary_path = Path(stream.name)
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary_path.replace(self.path)
        except (OSError, TypeError, ValueError) as exc:
            LOGGER.warning("semantic cache persistence failed for %s: %s", self.path, exc)
            return False
        finally:
            if temporary_path is not None:
                with suppress(OSError):
                    temporary_path.unlink(missing_ok=True)
        return True


class CachedSemanticProvider:
    """Add normalized, privacy-preserving cache reuse to a semantic provider."""

    def __init__(
        self,
        provider: OpenAICompatibleProvider,
        cache: SemanticCache,
        model: str,
        configuration: Mapping[str, object],
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.model = model
        self.configuration = configuration

    def evaluate_many(
        self,
        requests: Sequence[SemanticRequest],
        max_concurrency: int = 4,
    ) -> list[SemanticResponse]:
        """Return cached and fresh responses in the original request order."""
        keys = [semantic_cache_key(request, self.model, self.configuration) for request in requests]
        responses: list[SemanticResponse | None] = [None] * len(requests)
        misses: list[tuple[int, SemanticRequest]] = []
        for index, (key, request) in enumerate(zip(keys, requests, strict=True)):
            cached = self.cache.get(key)
            if cached is None:
                misses.append((index, request))
            else:
                responses[index] = cached

        if misses:
            fresh = self.provider.evaluate_many([request for _, request in misses], max_concurrency=max_concurrency)
            if len(fresh) != len(misses):
                raise SemanticProviderError("provider returned an unexpected response count")
            for (index, _), response in zip(misses, fresh, strict=True):
                responses[index] = response
                self.cache.put(keys[index], response)

        if any(response is None for response in responses):
            raise SemanticProviderError("semantic evaluation produced an incomplete response set")
        return [cast(SemanticResponse, response) for response in responses]
