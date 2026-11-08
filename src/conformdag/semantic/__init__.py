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
from conformdag.semantic.provider import (
    OpenAICompatibleProvider,
    SemanticProviderError,
    strict_semantic_response_schema,
)

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
