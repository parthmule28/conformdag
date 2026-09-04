"""Tests for semantic policy request and finding normalization."""

from collections.abc import Sequence
from pathlib import Path

from conformdag.models import (
    Confidence,
    EnforcementType,
    Policy,
    SemanticAuditEvidence,
    SemanticRequest,
    SemanticResponse,
)
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
    return SemanticContext("[SOURCE dag.py]\nlogging.info(token='[REDACTED]')", "context", ("dag.py",), ())


def test_builds_policy_specific_untrusted_request() -> None:
    policy = next(item for item in _policies() if item.id == "AIR-SEM-001")

    request = build_semantic_request(policy, _context())

    assert request.policy_id == "AIR-SEM-001"
    assert request.policy_version == policy.version
    assert len(request.policy_contract_hash) == 64
    assert len(request.enforcement_hash) == 64
    assert request.prompt_version == "3"
    assert "[SOURCE dag.py]" not in request.system_prompt
    assert request.evidence.startswith("[SOURCE")
    assert "external_write_markers" in request.system_prompt
    assert "insert" in request.system_prompt
    assert "return NEEDS_REVIEW" in request.system_prompt


def test_idempotence_without_evidence_abstains() -> None:
    policy = next(item for item in _policies() if item.id == "AIR-SEM-001")
    response = SemanticResponse(
        status="PASS",
        evidence="",
        explanation="No duplicate write observed.",
        confidence=Confidence.HIGH,
    )

    finding = semantic_finding(policy, response, _context())

    assert finding.status.value == "NEEDS_REVIEW"
    assert finding.confidence is Confidence.HIGH
    assert "without bounded evidence" in (finding.explanation or "")


def test_orchestration_request_includes_structural_signal_hints() -> None:
    policy = next(item for item in _policies() if item.id == "AIR-SEM-002")
    context = SemanticContext(
        "[SOURCE dag.py]\nfor row in rows:\n    database-query(row)",
        "context",
        ("dag.py",),
        (),
    )

    request = build_semantic_request(policy, context)

    assert "Deterministic structural signals are hints" in request.system_prompt
    assert '"for-loop": 1' in request.system_prompt
    assert '"database-query": 1' in request.system_prompt


def test_sensitive_logging_request_redacts_before_provider_boundary() -> None:
    policy = next(item for item in _policies() if item.id == "AIR-SEM-003")
    context = SemanticContext(
        "[SOURCE dag.py]\nlogging.info(token='unmasked-secret')",
        "context",
        ("dag.py",),
        (),
    )

    request = build_semantic_request(policy, context)

    assert "unmasked-secret" not in request.evidence
    assert "[REDACTED]" in request.evidence
    assert "unmasked-secret" not in request.system_prompt
    assert "logging" in request.system_prompt


def test_abstraction_request_uses_declared_registry_and_abstains_when_uncertain() -> None:
    policy = next(item for item in _policies() if item.id == "AIR-SEM-004")
    request = build_semantic_request(policy, _context())

    assert "company.operators.SafePythonOperator" in request.system_prompt
    assert "Do not infer approval from frequency or naming" in request.system_prompt
    assert "return NEEDS_REVIEW" in request.system_prompt


def test_semantic_finding_normalizes_audit_citations_and_marks_unknown_locations() -> None:
    policy = next(item for item in _policies() if item.id == "AIR-SEM-001")
    response = SemanticResponse(
        status="NEEDS_REVIEW",
        evidence="retry evidence",
        explanation="The retry contract is not visible.",
        confidence=Confidence.LOW,
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

    finding = semantic_finding(policy, response, _context())

    assert len(finding.audit_evidence) == 2
    assert finding.audit_evidence[0].unresolved is False
    assert finding.audit_evidence[1].unresolved is True
    assert finding.audit_evidence[1].location == "missing.py"


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
