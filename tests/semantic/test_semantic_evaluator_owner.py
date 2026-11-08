"""C22 owner tests for semantic policy evaluation and the legacy shim."""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import conformdag.semantic_evaluator as legacy_shim
from conformdag.models import (
    Confidence,
    EnforcementType,
    Policy,
    SemanticAuditEvidence,
    SemanticRequest,
    SemanticResponse,
)
from conformdag.policy import load_policy_pack


def _owner() -> Any:
    return importlib.import_module("conformdag.semantic.evaluator")


def _policies() -> list[Policy]:
    pack = load_policy_pack(Path("policies/pack.yaml"), Path.cwd())
    return [policy for policy in pack.policies if policy.id.startswith("AIR-SEM-")]


def _context() -> Any:
    owner = _owner()
    return owner.SemanticContext("[SOURCE dag.py]\nlogging.info(token='[REDACTED]')", "context", ("dag.py",), ())


def test_evaluator_owner_is_the_source_of_every_legacy_evaluator_name() -> None:
    owner = _owner()
    for name in (
        "POLICY_INSTRUCTIONS",
        "SemanticProvider",
        "SemanticEvaluationResult",
        "select_semantic_policies",
        "build_semantic_request",
        "semantic_finding",
        "run_semantic_evaluation",
        "evaluate_semantic_policies",
    ):
        assert getattr(owner, name) is getattr(legacy_shim, name)


def test_evaluator_owner_does_not_duplicate_model_or_context_types() -> None:
    owner = _owner()
    context = importlib.import_module("conformdag.semantic.context")
    provider = importlib.import_module("conformdag.semantic.provider")

    assert owner.SemanticContext is context.SemanticContext
    assert owner.SemanticProviderError is provider.SemanticProviderError
    assert owner.SemanticRequest is legacy_shim.SemanticRequest


def test_policy_instructions_are_unchanged() -> None:
    owner = _owner()

    assert owner.POLICY_INSTRUCTIONS == {
        "AIR-SEM-001": (
            "Review external writes, retry behavior, and deduplication evidence for idempotence. "
            "Conclude PASS or FAIL only when the supplied evidence establishes the write behavior "
            "and retry/deduplication controls; otherwise return NEEDS_REVIEW and name the missing "
            "evidence."
        ),
        "AIR-SEM-002": ("Review structural signals and evidence for business logic embedded in orchestration."),
        "AIR-SEM-003": (
            "Review configured logging calls for sensitive values. Evidence has already been "
            "redacted locally; never reconstruct or repeat a masked value."
        ),
        "AIR-SEM-004": (
            "Review usage cues and documentation against the policy-declared abstraction registry. "
            "Do not infer approval from frequency or naming; return NEEDS_REVIEW when equivalence "
            "to a registered abstraction cannot be established from the evidence."
        ),
    }


def test_semantic_provider_protocol_contract_is_unchanged() -> None:
    owner = _owner()

    assert owner.SemanticProvider.evaluate_many.__annotations__["max_concurrency"] == "int"


def test_request_construction_redacts_and_delimits_untrusted_evidence() -> None:
    owner = _owner()
    policy = next(item for item in _policies() if item.id == "AIR-SEM-003")
    context = owner.SemanticContext(
        "[SOURCE dag.py]\ncredential=c15-test-request-credential",
        "provided-context-hash",
        ("dag.py",),
        (),
    )

    request = owner.build_semantic_request(policy, context)

    assert request.policy_id == "AIR-SEM-003"
    assert request.prompt_version == "3"
    assert "c15-test-request-credential" not in request.evidence
    assert "[REDACTED]" in request.evidence
    assert "[SOURCE dag.py]" not in request.system_prompt
    assert "logging" in request.system_prompt


def test_finding_redaction_citation_resolution_and_fingerprint_are_unchanged() -> None:
    owner = _owner()
    policy = next(item for item in _policies() if item.id == "AIR-SEM-001")
    response = SemanticResponse(
        status="FAIL",
        evidence="credential=c15-test-finding-evidence",
        explanation="credential=c15-test-finding-explanation",
        remediation="credential=c15-test-finding-remediation",
        confidence=Confidence.HIGH,
        audit_evidence=[
            SemanticAuditEvidence(
                criterion="retry-safety",
                source_type="source",
                location="dag.py",
                excerpt="retry configuration is not shown",
            ),
            SemanticAuditEvidence(
                criterion="invented",
                source_type="source",
                location="missing.py",
                excerpt="unsupported citation",
            ),
        ],
    )

    finding = owner.semantic_finding(policy, response, _context(), Path("dag.py"))

    assert finding.enforcement is EnforcementType.SEMANTIC
    assert [item.unresolved for item in finding.audit_evidence] == [False, True]
    assert finding.explanation is not None
    assert "c15-test-finding-explanation" not in finding.explanation
    assert "[REDACTED]" in finding.explanation
    assert len(finding.fingerprint) == 64


class _Provider:
    def evaluate_many(
        self,
        requests: Sequence[SemanticRequest],
        max_concurrency: int = 4,
    ) -> list[SemanticResponse]:
        return [
            SemanticResponse(
                status="PASS",
                evidence=f"evidence-{request.policy_id}",
                explanation="supported",
                confidence=Confidence.HIGH,
            )
            for request in requests
        ]


def test_run_semantic_evaluation_preserves_order_and_metadata() -> None:
    owner = _owner()

    result = owner.run_semantic_evaluation(_policies(), _context(), _Provider(), temperature=0.2, max_output_tokens=512)

    assert [policy.id for policy in result.policies] == [
        "AIR-SEM-001",
        "AIR-SEM-002",
        "AIR-SEM-003",
        "AIR-SEM-004",
    ]
    assert [request.policy_id for request in result.requests] == [policy.id for policy in result.policies]
    assert [response.evidence for response in result.responses] == [
        f"evidence-{policy.id}" for policy in result.policies
    ]
    assert [finding.policy_id for finding in result.findings] == [policy.id for policy in result.policies]
    assert all(request.temperature == 0.2 for request in result.requests)
    assert all(request.max_output_tokens == 512 for request in result.requests)
