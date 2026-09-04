"""Provider-backed benchmark baseline execution with normalized cache reuse."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

from conformdag.models import Policy, SemanticRequest, SemanticResponse
from conformdag.policy import policy_contract_hash, policy_enforcement_hash
from conformdag.semantic import (
    GENERIC_REVIEWER_PROMPT,
    SemanticCache,
    SemanticContext,
    semantic_cache_key,
)
from conformdag.semantic_evaluator import SemanticProvider


class BenchmarkBaselineError(RuntimeError):
    """Raised when a provider-backed benchmark cannot preserve provenance."""


@dataclass(frozen=True)
class SemanticBaselineResult:
    """Normalized responses and provenance for one semantic baseline run."""

    mode: str
    requested_model: str
    served_models: tuple[str, ...]
    responses: tuple[SemanticResponse, ...]
    cache_hits: int
    total_requests: int
    prompt_hashes: tuple[str, ...]

    @property
    def cache_reuse_rate(self) -> float:
        return self.cache_hits / self.total_requests if self.total_requests else 0.0


def build_generic_reviewer_request(policy: Policy, context: SemanticContext) -> SemanticRequest:
    """Build a request for the pinned generic-reviewer baseline."""
    return SemanticRequest(
        policy_id=policy.id,
        policy_version=policy.version,
        policy_contract_hash=policy_contract_hash(policy),
        enforcement_hash=policy_enforcement_hash(policy),
        prompt_version=GENERIC_REVIEWER_PROMPT.version,
        context_hash=context.context_hash,
        system_prompt=GENERIC_REVIEWER_PROMPT.render(policy.invariant),
        evidence=context.text,
    )


def run_semantic_baseline(
    requests: list[SemanticRequest],
    provider: SemanticProvider,
    *,
    mode: str,
    model: str,
    configuration: Mapping[str, object],
    cache: SemanticCache | None = None,
) -> SemanticBaselineResult:
    """Run LLM-only or hybrid requests with exact model and normalized cache checks."""
    if mode not in {"llm-only", "hybrid", "generic-reviewer"}:
        raise ValueError("benchmark semantic mode must be llm-only, hybrid, or generic-reviewer")

    keys = [semantic_cache_key(request, model, configuration) for request in requests]
    responses: list[SemanticResponse | None] = [None] * len(requests)
    misses: list[tuple[int, SemanticRequest]] = []
    cache_hits = 0
    if cache is not None:
        for index, key in enumerate(keys):
            cached = cache.get(key)
            if cached is None:
                misses.append((index, requests[index]))
            else:
                responses[index] = cached
                cache_hits += 1
    else:
        misses = list(enumerate(requests))

    if misses:
        evaluated = provider.evaluate_many([request for _, request in misses], max_concurrency=4)
        if len(evaluated) != len(misses):
            raise BenchmarkBaselineError("provider returned an unexpected response count")
        for (index, _), response in zip(misses, evaluated, strict=True):
            if response.served_model != model:
                raise BenchmarkBaselineError(f"provider served model {response.served_model!r}, requested {model!r}")
            responses[index] = response
            if cache is not None:
                cache.put(keys[index], response)

    normalized = tuple(response for response in responses if response is not None)
    if len(normalized) != len(requests):
        raise BenchmarkBaselineError("benchmark produced an incomplete response set")
    served_models = tuple(sorted({response.served_model or model for response in normalized}))
    prompt_hashes = tuple(hashlib.sha256(request.system_prompt.encode("utf-8")).hexdigest() for request in requests)
    return SemanticBaselineResult(
        mode=mode,
        requested_model=model,
        served_models=served_models,
        responses=normalized,
        cache_hits=cache_hits,
        total_requests=len(requests),
        prompt_hashes=prompt_hashes,
    )
