"""Policy-facing semantic request construction and advisory finding normalization."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from conformdag.evaluator import redact_evidence
from conformdag.models import (
    EnforcementType,
    Finding,
    FindingEvidence,
    FindingLocation,
    FindingStatus,
    Policy,
    SemanticRequest,
    SemanticResponse,
)
from conformdag.policy import policy_contract_hash, policy_enforcement_hash
from conformdag.semantic import (
    DEFAULT_PROMPT_TEMPLATE,
    SemanticContext,
    SemanticProviderError,
)

POLICY_INSTRUCTIONS = {
    "AIR-SEM-001": (
        "Review external writes, retry behavior, and deduplication evidence for idempotence."
    ),
    "AIR-SEM-002": (
        "Review structural signals and evidence for business logic embedded in orchestration."
    ),
    "AIR-SEM-003": "Review logging evidence for sensitive values after local redaction.",
    "AIR-SEM-004": (
        "Review usage cues and documentation against the policy-declared abstraction registry."
    ),
}


class SemanticProvider(Protocol):
    def evaluate_many(
        self,
        requests: Sequence[SemanticRequest],
        max_concurrency: int = 4,
    ) -> list[SemanticResponse]:
        """Evaluate requests in deterministic input order."""
        ...


def build_semantic_request(policy: Policy, context: SemanticContext) -> SemanticRequest:
    """Build a strict request with source content delimited as untrusted evidence."""
    instruction = POLICY_INSTRUCTIONS.get(policy.id, policy.invariant)
    system_prompt = DEFAULT_PROMPT_TEMPLATE.render(f"{policy.invariant}\n{instruction}")
    return SemanticRequest(
        policy_id=policy.id,
        policy_version=policy.version,
        policy_contract_hash=policy_contract_hash(policy),
        enforcement_hash=policy_enforcement_hash(policy),
        prompt_version=DEFAULT_PROMPT_TEMPLATE.version,
        context_hash=context.context_hash,
        system_prompt=system_prompt,
        evidence=context.text,
    )


def semantic_finding(
    policy: Policy,
    response: SemanticResponse,
    context: SemanticContext,
    source_path: Path | None = None,
) -> Finding:
    """Normalize a provider decision as advisory evidence with a stable identity."""
    status = FindingStatus(response.status)
    evidence = redact_evidence(response.evidence)
    fingerprint_value = (
        f"{policy.id}:{policy.version}:{context.context_hash}:{status.value}:{evidence}"
    )
    fingerprint = hashlib.sha256(fingerprint_value.encode("utf-8")).hexdigest()
    return Finding(
        policy_id=policy.id,
        policy_version=policy.version,
        status=status,
        severity=policy.severity,
        enforcement=EnforcementType.SEMANTIC,
        location=FindingLocation(file=source_path),
        evidence=FindingEvidence(text=evidence),
        explanation=response.explanation,
        remediation=response.remediation or policy.safe_path,
        confidence=response.confidence,
        fingerprint=fingerprint,
    )


def evaluate_semantic_policies(
    policies: Sequence[Policy],
    context: SemanticContext,
    provider: SemanticProvider,
    source_path: Path | None = None,
) -> list[Finding]:
    """Evaluate active semantic policies in policy order and preserve result order."""
    selected = [
        policy
        for policy in sorted(policies, key=lambda item: item.id)
        if policy.status.value == "ACTIVE"
        and policy.enforcement.type
        in (
            EnforcementType.SEMANTIC,
            EnforcementType.HYBRID,
        )
    ]
    requests = [build_semantic_request(policy, context) for policy in selected]
    try:
        responses = provider.evaluate_many(requests, max_concurrency=4)
    except SemanticProviderError:
        raise
    return [
        semantic_finding(policy, response, context, source_path)
        for policy, response in zip(selected, responses, strict=True)
    ]
