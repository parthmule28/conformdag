"""Tests for semantic policy request and finding normalization."""

from collections.abc import Sequence
from pathlib import Path

from conformdag.models import Confidence, EnforcementType, Policy, SemanticRequest, SemanticResponse
from conformdag.policy import load_policy_pack
from conformdag.semantic import SemanticContext
from conformdag.semantic_evaluator import (
    build_semantic_request,
    evaluate_semantic_policies,
    semantic_finding,
)


def _policies() -> list[Policy]:
    pack = load_policy_pack(Path("policies/pack.yaml"), Path.cwd())
    return [policy for policy in pack.policies if policy.id.startswith("AIR-SEM-")]


def _context() -> SemanticContext:
    return SemanticContext(
        "[SOURCE dag.py]\nlogging.info(token='[REDACTED]')", "context", ("dag.py",), ()
    )


def test_builds_policy_specific_untrusted_request() -> None:
    policy = next(item for item in _policies() if item.id == "AIR-SEM-001")

    request = build_semantic_request(policy, _context())

    assert request.policy_id == "AIR-SEM-001"
    assert request.prompt_version == "1"
    assert "[SOURCE dag.py]" not in request.system_prompt
    assert request.evidence.startswith("[SOURCE")


def test_normalizes_abstention_as_advisory_finding() -> None:
    policy = next(item for item in _policies() if item.id == "AIR-SEM-004")
    response = SemanticResponse(
        status="NEEDS_REVIEW",
        evidence="equivalence is uncertain",
        explanation="The abstraction usage cannot be established from available evidence.",
        remediation="Document the abstraction contract.",
        confidence=Confidence.LOW,
    )

    finding = semantic_finding(policy, response, _context(), Path("dags/example.py"))

    assert finding.status.value == "NEEDS_REVIEW"
    assert finding.enforcement is EnforcementType.SEMANTIC
    assert finding.confidence is Confidence.LOW
    assert finding.location.file == Path("dags/example.py")


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


def test_semantic_policy_results_are_deterministically_ordered() -> None:
    findings = evaluate_semantic_policies(_policies(), _context(), _Provider())

    assert [finding.policy_id for finding in findings] == [
        "AIR-SEM-001",
        "AIR-SEM-002",
        "AIR-SEM-003",
        "AIR-SEM-004",
    ]
