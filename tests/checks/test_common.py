"""Direct tests for shared deterministic-check contracts."""

from conformdag.checks.common import fix_target, redact_evidence


def test_fix_target_preserves_structural_remediation_coordinates() -> None:
    target = fix_target(12, "dag", "dag-call")

    assert target.line == 12
    assert target.enclosing == "dag"
    assert target.node == "dag-call"


def test_redact_evidence_bounds_and_masks_credentials() -> None:
    evidence = redact_evidence("password='secret-value' " + "x" * 500, max_chars=80)

    assert "[REDACTED]" in evidence
    assert "secret-value" not in evidence
    assert len(evidence) <= 80
