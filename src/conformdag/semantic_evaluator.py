"""Policy-facing semantic request construction and advisory finding normalization."""

from __future__ import annotations

import hashlib
import json
import re
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
        "Review external writes, retry behavior, and deduplication evidence for idempotence. "
        "Conclude PASS or FAIL only when the supplied evidence establishes the write behavior "
        "and retry/deduplication controls; otherwise return NEEDS_REVIEW and name the missing "
        "evidence."
    ),
    "AIR-SEM-002": (
        "Review structural signals and evidence for business logic embedded in orchestration."
    ),
    "AIR-SEM-003": "Review logging evidence for sensitive values after local redaction.",
    "AIR-SEM-004": (
        "Review usage cues and documentation against the policy-declared abstraction registry."
    ),
}


def _policy_instruction(policy: Policy, context_text: str) -> str:
    instruction = POLICY_INSTRUCTIONS.get(policy.id, policy.invariant)
    configuration = json.dumps(policy.configuration.model_dump(mode="json"), sort_keys=True)
    details = f"{instruction}\nPolicy configuration:\n{configuration}"
    if policy.id == "AIR-SEM-002":
        raw_configuration = policy.configuration.model_dump(mode="json")
        patterns = [str(item) for item in raw_configuration.get("signal_patterns", [])]
        source_lines = sum(
            1 for line in context_text.splitlines() if not line.startswith("[SOURCE ")
        )
        signal_counts = {
            pattern: (
                len(re.findall(r"\bfor\s+", context_text))
                if pattern == "for-loop"
                else context_text.lower().count(pattern.lower())
            )
            for pattern in patterns
        }
        details += "\nDeterministic structural signals are hints, not conclusions:\n" + json.dumps(
            {"source_line_count": source_lines, "signal_counts": signal_counts},
            sort_keys=True,
        )
    return details


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
    system_prompt = DEFAULT_PROMPT_TEMPLATE.render(
        f"{policy.invariant}\n{_policy_instruction(policy, context.text)}"
    )
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
    explanation = response.explanation
    if policy.id == "AIR-SEM-001" and not response.evidence.strip():
        status = FindingStatus.NEEDS_REVIEW
        explanation = f"{explanation} Idempotence cannot be decided without bounded evidence."
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
        explanation=explanation,
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
