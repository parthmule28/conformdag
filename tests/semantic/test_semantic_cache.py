"""C22 owner tests for semantic cache identity and persistence."""

from __future__ import annotations

import importlib
import json
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

import conformdag.semantic as facade
from conformdag.models import Confidence, SemanticAuditEvidence, SemanticRequest, SemanticResponse


def _owner() -> Any:
    return importlib.import_module("conformdag.semantic.cache")


def _request() -> SemanticRequest:
    return SemanticRequest(
        policy_id="AIR-SEM-001",
        prompt_version="3",
        context_hash="context-hash",
        system_prompt="Return only the requested JSON decision.",
        evidence="safe evidence",
    )


def _response() -> SemanticResponse:
    return SemanticResponse(
        status="PASS",
        evidence="bounded evidence",
        explanation="safe",
        confidence=Confidence.HIGH,
    )


def test_cache_owner_module_owns_the_public_cache_objects() -> None:
    owner = _owner()

    assert owner.semantic_cache_key is facade.semantic_cache_key
    assert owner.SemanticCache is facade.SemanticCache
    assert owner.CachedSemanticProvider is facade.CachedSemanticProvider
    assert owner.LOGGER is facade.LOGGER


def test_cache_key_is_frozen_and_depends_on_contract_inputs() -> None:
    owner = _owner()
    request = _request()

    assert owner.semantic_cache_key(request, "test-model", {"temperature": 0.0}) == (
        "ee1190cb91cda37404d69d63a6ef7345729cfc3625ee6d6c54a4fecb86605237"
    )
    assert owner.semantic_cache_key(
        request.model_copy(update={"context_hash": "other"}), "test-model", {"temperature": 0.0}
    ) != owner.semantic_cache_key(request, "test-model", {"temperature": 0.0})
    assert owner.semantic_cache_key(request, "other-model", {"temperature": 0.0}) != owner.semantic_cache_key(
        request, "test-model", {"temperature": 0.0}
    )
    assert owner.semantic_cache_key(request, "test-model", {"temperature": 0.1}) != owner.semantic_cache_key(
        request, "test-model", {"temperature": 0.0}
    )


def test_cache_stores_only_normalized_redacted_responses(tmp_path: Path) -> None:
    owner = _owner()
    cache = owner.SemanticCache(tmp_path / "semantic-cache.json")
    response = SemanticResponse(
        status="PASS",
        evidence="credential=c15-test-cache-evidence",
        explanation="credential=c15-test-cache-explanation",
        remediation="credential=c15-test-cache-remediation",
        confidence=Confidence.HIGH,
        audit_evidence=[
            SemanticAuditEvidence(
                criterion="summary",
                source_type="provider",
                excerpt="serviceCredential=c15-test-cache-audit",
            )
        ],
    )

    assert cache.put("key", response) is True

    stored = (tmp_path / "semantic-cache.json").read_text(encoding="utf-8")
    for secret in (
        "c15-test-cache-evidence",
        "c15-test-cache-explanation",
        "c15-test-cache-remediation",
        "c15-test-cache-audit",
    ):
        assert secret not in stored
    assert "[REDACTED]" in stored
    assert "system_prompt" not in stored
    assert "raw_prompt" not in stored
    assert "raw_response" not in stored

    cached = cache.get("key")
    assert cached is not None
    assert cached.cache_hit is True
    assert cached.model_copy(update={"cache_hit": False}) == response.model_copy(
        update={
            "evidence": "credential=[REDACTED]",
            "explanation": "credential=[REDACTED]",
            "remediation": "credential=[REDACTED]",
            "audit_evidence": [
                SemanticAuditEvidence(
                    criterion="summary",
                    source_type="provider",
                    excerpt="serviceCredential=[REDACTED]",
                )
            ],
        }
    )


def test_cache_handles_corrupt_and_non_mapping_files_gracefully(tmp_path: Path) -> None:
    owner = _owner()
    path = tmp_path / "semantic-cache.json"
    cache = owner.SemanticCache(path)

    path.write_text("{not json", encoding="utf-8")
    assert cache.get("missing") is None

    path.write_text("[]", encoding="utf-8")
    assert cache.get("missing") is None


def test_cache_concurrent_writes_merge_without_losing_entries(tmp_path: Path) -> None:
    owner = _owner()
    cache = owner.SemanticCache(tmp_path / "semantic-cache.json")

    def write(index: int) -> bool:
        return cache.put(f"key-{index}", _response().model_copy(update={"evidence": f"bounded-{index}"}))

    with ThreadPoolExecutor(max_workers=4) as executor:
        assert all(executor.map(write, range(8)))

    assert all(cache.get(f"key-{index}") is not None for index in range(8))


def test_cache_write_failure_is_nonfatal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    owner = _owner()
    cache = owner.SemanticCache(tmp_path / "semantic-cache.json")

    def fail_replace(_self: Path, _target: Path) -> Path:
        raise OSError("read-only cache")

    monkeypatch.setattr(Path, "replace", fail_replace)

    assert cache.put("key", _response()) is False


class _CountingProvider:
    def __init__(self, responses: Sequence[SemanticResponse] | None = None) -> None:
        self.calls = 0
        self.requests: list[SemanticRequest] = []
        self._responses = responses

    def evaluate_many(
        self,
        requests: Sequence[SemanticRequest],
        max_concurrency: int = 4,
    ) -> list[SemanticResponse]:
        self.calls += 1
        self.requests.extend(requests)
        if self._responses is not None:
            return list(self._responses)
        return [
            SemanticResponse(
                status="PASS",
                evidence=f"fresh-{request.context_hash}",
                explanation="safe",
                confidence=Confidence.HIGH,
            )
            for request in requests
        ]


def test_cached_provider_preserves_order_and_only_calls_provider_for_misses(tmp_path: Path) -> None:
    owner = _owner()
    cache = owner.SemanticCache(tmp_path / "semantic-cache.json")
    provider = _CountingProvider()
    cached_provider = owner.CachedSemanticProvider(provider, cache, "test-model", {"temperature": 0.0})
    first = _request()
    second = first.model_copy(update={"context_hash": "other-context"})

    first_batch = cached_provider.evaluate_many([first, second], max_concurrency=2)
    assert provider.calls == 1
    assert [item.evidence for item in first_batch] == ["fresh-context-hash", "fresh-other-context"]

    second_batch = cached_provider.evaluate_many([second, first], max_concurrency=2)
    assert provider.calls == 1
    assert [item.evidence for item in second_batch] == ["fresh-other-context", "fresh-context-hash"]
    assert all(item.cache_hit is True for item in second_batch)


def test_cached_provider_rejects_incomplete_provider_response_sets(tmp_path: Path) -> None:
    owner = _owner()
    cache = owner.SemanticCache(tmp_path / "semantic-cache.json")
    provider = _CountingProvider(responses=[])
    cached_provider = owner.CachedSemanticProvider(provider, cache, "test-model", {"temperature": 0.0})

    with pytest.raises(owner.SemanticProviderError, match="unexpected response count"):
        cached_provider.evaluate_many([_request()])


def test_cache_file_format_is_sorted_and_newline_terminated(tmp_path: Path) -> None:
    owner = _owner()
    cache = owner.SemanticCache(tmp_path / "semantic-cache.json")

    cache.put("b", _response())
    cache.put("a", _response())

    stored = (tmp_path / "semantic-cache.json").read_text(encoding="utf-8")
    assert stored.endswith("\n")
    payload = json.loads(stored)
    assert list(payload) == ["a", "b"]
