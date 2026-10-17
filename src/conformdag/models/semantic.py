"""Semantic model values."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, NonNegativeInt, PositiveInt

from .common import Confidence, ConformModel


def _empty_audit_evidence() -> list[SemanticAuditEvidence]:
    return []


# Sibling models share the same named factory without importing a private symbol.
empty_audit_evidence = _empty_audit_evidence


class SemanticAuditEvidence(ConformModel):
    criterion: str
    source_type: Literal["source", "runtime", "policy", "provider"]
    location: str | None = None
    excerpt: str = Field(max_length=240)
    unresolved: bool = False


class SemanticRunMetadata(ConformModel):
    policy_id: str
    requested_model: str
    served_model: str | None = None
    context_hash: str
    prompt_hash: str
    usage: dict[str, NonNegativeInt] = Field(default_factory=dict)
    retries: NonNegativeInt = 0
    latency_ms: NonNegativeInt = 0
    cache_hit: bool = False
    repeatability: Literal["not-measured", "repeatable", "varied"] = "not-measured"
    pricing_provenance: str | None = None


class SemanticRequest(ConformModel):
    schema_version: Literal["1"] = "1"
    policy_id: str
    policy_version: str = "unknown"
    policy_contract_hash: str = ""
    enforcement_hash: str = ""
    prompt_version: str
    context_hash: str
    system_prompt: str
    evidence: str
    max_output_tokens: PositiveInt = 4000
    temperature: float = 0.0


class SemanticResponse(ConformModel):
    status: Literal["PASS", "FAIL", "NEEDS_REVIEW", "NOT_APPLICABLE"]
    evidence: str
    explanation: str
    remediation: str | None = None
    confidence: Confidence
    audit_evidence: list[SemanticAuditEvidence] = Field(default_factory=_empty_audit_evidence)
    served_model: str | None = None
    usage: dict[str, NonNegativeInt] = Field(default_factory=dict)
    retries: NonNegativeInt = 0
    latency_ms: NonNegativeInt = 0
    cache_hit: bool = False
    repeatability: Literal["not-measured", "repeatable", "varied"] = "not-measured"
    pricing_provenance: str | None = None
