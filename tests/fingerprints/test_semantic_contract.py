"""Compatibility tests for semantic finding fingerprints."""

import hashlib
import json
from pathlib import Path
from typing import Literal

from conformdag.models import (
    Confidence,
    EnforcementConfig,
    EnforcementType,
    Policy,
    SemanticAuditEvidence,
    SemanticResponse,
    Severity,
)
from conformdag.semantic import SemanticContext
from conformdag.semantic_evaluator import semantic_finding


def _policy(policy_id: str = "C19-SEM-001", version: str = "3.2.1") -> Policy:
    return Policy.model_construct(
        id=policy_id,
        version=version,
        severity=Severity.MEDIUM,
        safe_path="Review the semantic fixture.",
        enforcement=EnforcementConfig(type=EnforcementType.SEMANTIC, blocking=True),
    )


def _context(
    *,
    context_hash: str = "context-hash-one",
    included_files: tuple[str, ...] = ("dags/sample.py",),
    text: str = "[SOURCE dags/sample.py]\noperation()",
) -> SemanticContext:
    return SemanticContext(text, context_hash, included_files, ())


def _response(
    *,
    status: Literal["PASS", "FAIL", "NEEDS_REVIEW", "NOT_APPLICABLE"] = "FAIL",
    evidence: str = "same provider evidence",
    explanation: str = "same provider explanation",
    remediation: str = "same remediation",
    confidence: Confidence = Confidence.HIGH,
    criterion: str = "retry-safety",
    location: str | None = "dags/sample.py",
    excerpt: str = "bounded source citation",
    unresolved: bool = False,
) -> SemanticResponse:
    return SemanticResponse(
        status=status,
        evidence=evidence,
        explanation=explanation,
        remediation=remediation,
        confidence=confidence,
        audit_evidence=[
            SemanticAuditEvidence(
                criterion=criterion,
                source_type="source",
                location=location,
                excerpt=excerpt,
                unresolved=unresolved,
            )
        ],
    )


def _finding(
    *,
    policy: Policy | None = None,
    response: SemanticResponse | None = None,
    context: SemanticContext | None = None,
    source_path: Path | None = Path("dags/sample.py"),
):
    return semantic_finding(
        policy if policy is not None else _policy(),
        response if response is not None else _response(),
        context if context is not None else _context(),
        source_path,
    )


def test_semantic_fingerprint_matches_independent_canonical_json_sha256_oracle() -> None:
    finding = _finding()
    payload = {
        "policy_id": "C19-SEM-001",
        "policy_version": "3.2.1",
        "finding_kind": "semantic",
        "status": "FAIL",
        "source_path": "dags/sample.py",
        "citations": [
            {
                "criterion": "retry-safety",
                "source_type": "source",
                "location": "dags/sample.py",
                "unresolved": False,
            }
        ],
    }
    expected = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    assert expected == "a647f8e06112394f51a3c2f37f7bd567771ee61ac7a406ba74e2d7b8c43cb38b"
    assert finding.fingerprint == expected


def test_identical_semantic_inputs_produce_the_same_fingerprint() -> None:
    assert _finding().fingerprint == _finding().fingerprint


def test_policy_id_changes_semantic_fingerprint() -> None:
    baseline = _finding()
    changed = _finding(policy=_policy(policy_id="C19-SEM-002"))

    assert changed.fingerprint != baseline.fingerprint


def test_policy_version_changes_semantic_fingerprint() -> None:
    baseline = _finding()
    changed = _finding(policy=_policy(version="3.2.2"))

    assert changed.fingerprint != baseline.fingerprint


def test_normalized_status_changes_semantic_fingerprint() -> None:
    baseline = _finding()
    changed = _finding(response=_response(status="PASS"))

    assert changed.fingerprint != baseline.fingerprint


def test_source_path_changes_semantic_fingerprint() -> None:
    context = _context(included_files=("dags/sample.py", "dags/other.py"))
    baseline = _finding(context=context, source_path=Path("dags/sample.py"))
    changed = _finding(context=context, source_path=Path("dags/other.py"))

    assert changed.fingerprint != baseline.fingerprint


def test_citation_location_changes_semantic_fingerprint() -> None:
    context = _context(included_files=("dags/sample.py", "dags/other.py"))
    baseline = _finding(context=context, response=_response(location="dags/sample.py"))
    changed = _finding(context=context, response=_response(location="dags/other.py"))

    assert changed.fingerprint != baseline.fingerprint


def test_citation_criterion_changes_semantic_fingerprint() -> None:
    baseline = _finding(response=_response(criterion="retry-safety"))
    changed = _finding(response=_response(criterion="data-isolation"))

    assert changed.fingerprint != baseline.fingerprint


def test_unresolved_citation_flag_changes_semantic_fingerprint() -> None:
    baseline = _finding(response=_response(unresolved=False))
    changed = _finding(response=_response(unresolved=True))

    assert changed.fingerprint != baseline.fingerprint


def test_reordering_citations_does_not_change_semantic_fingerprint() -> None:
    first = _response()
    first.audit_evidence.append(
        SemanticAuditEvidence(
            criterion="data-isolation",
            source_type="source",
            location="dags/sample.py",
            excerpt="second citation",
        )
    )
    reversed_response = first.model_copy(update={"audit_evidence": list(reversed(first.audit_evidence))})

    assert _finding(response=first).fingerprint == _finding(response=reversed_response).fingerprint


def test_provider_prose_confidence_remediation_and_citation_excerpt_are_excluded() -> None:
    baseline_response = _response()
    baseline = _finding(response=baseline_response)
    changed_responses = (
        _response(explanation="different provider explanation"),
        _response(confidence=Confidence.LOW),
        _response(remediation="different remediation prose"),
        _response(excerpt="different citation excerpt"),
    )

    assert all(_finding(response=response).fingerprint == baseline.fingerprint for response in changed_responses)


def test_unrelated_source_context_change_does_not_change_semantic_fingerprint() -> None:
    cited_context = _context(context_hash="hash-one", included_files=("dags/sample.py",))
    unrelated_edit = _context(
        context_hash="hash-two",
        included_files=("dags/sample.py", "dags/unrelated.py"),
        text="[SOURCE dags/sample.py]\noperation()\n[SOURCE dags/unrelated.py]\nchanged()",
    )

    assert _finding(context=cited_context).fingerprint == _finding(context=unrelated_edit).fingerprint


def test_air_sem_001_missing_evidence_normalizes_status_and_changes_identity() -> None:
    policy = _policy(policy_id="AIR-SEM-001")
    evidenced = _finding(policy=policy, response=_response(status="PASS", evidence="bounded evidence"))
    missing = _finding(policy=policy, response=_response(status="PASS", evidence=""))

    assert evidenced.status.value == "PASS"
    assert missing.status.value == "NEEDS_REVIEW"
    assert missing.fingerprint != evidenced.fingerprint
