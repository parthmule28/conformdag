"""Fixed reports used to characterize the public reporting contract."""

from datetime import UTC, datetime
from pathlib import Path

from conformdag.models import (
    EnforcementType,
    Finding,
    FindingEvidence,
    FindingLocation,
    FindingStatus,
    GateResult,
    GateRuleResult,
    RunIssue,
    RunMetadata,
    RuntimeObservation,
    ScanReport,
    Severity,
    Suppression,
)

FIXED_TIMESTAMP = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def fixed_suppression() -> Suppression:
    """Return the stable suppression attached to the fixed report."""
    return Suppression(
        fingerprint="fp-b-suppressed",
        policy_id="B-POLICY",
        reason="tracked fixture exception",
        owner="platform",
        created_at=datetime(2025, 12, 1, tzinfo=UTC),
        expires_at=datetime(2026, 12, 31, tzinfo=UTC),
    )


def _finding(
    *,
    policy_id: str,
    status: FindingStatus,
    severity: Severity,
    file: str,
    start_line: int,
    fingerprint: str,
    explanation: str,
    remediation: str,
    evidence: str,
    blocking: bool = False,
    suppressed: bool = False,
    suppression: Suppression | None = None,
) -> Finding:
    return Finding(
        policy_id=policy_id,
        policy_version="1.2.3",
        status=status,
        severity=severity,
        enforcement=EnforcementType.DETERMINISTIC,
        location=FindingLocation(file=Path(file), start_line=start_line, end_line=start_line + 1),
        evidence=FindingEvidence(
            text=evidence,
            start_line=start_line,
            end_line=start_line + 1,
            code_hash=f"code-{fingerprint}",
        ),
        explanation=explanation,
        remediation=remediation,
        fingerprint=fingerprint,
        blocking=blocking,
        suppressed=suppressed,
        suppression=suppression,
    )


def fixed_report() -> ScanReport:
    """Return a nontrivial deterministic report with intentionally unsorted inputs."""
    suppression = fixed_suppression()
    findings = [
        _finding(
            policy_id="B-POLICY",
            status=FindingStatus.FAIL,
            severity=Severity.HIGH,
            file="dags/b.py",
            start_line=12,
            fingerprint="fp-b-suppressed",
            explanation="password=fixture-explanation <unsafe>",
            remediation="credential=fixture-remediation",
            evidence="api_key=fixture-evidence <unsafe>",
            blocking=True,
            suppressed=True,
            suppression=suppression,
        ),
        _finding(
            policy_id="Z-PASS",
            status=FindingStatus.PASS,
            severity=Severity.INFO,
            file="dags/z.py",
            start_line=3,
            fingerprint="fp-z-pass",
            explanation="pass <safe>",
            remediation="no action",
            evidence="pass evidence",
        ),
        _finding(
            policy_id="A-POLICY",
            status=FindingStatus.ERROR,
            severity=Severity.CRITICAL,
            file="dags/a.py",
            start_line=7,
            fingerprint="fp-a-error",
            explanation="Bearer fixture-bearer",
            remediation="token=fixture-token-remediation",
            evidence="secret=fixture-secret-evidence",
            blocking=True,
        ),
        _finding(
            policy_id="B-POLICY",
            status=FindingStatus.FAIL,
            severity=Severity.LOW,
            file="dags/b.py",
            start_line=12,
            fingerprint="fp-b-tie",
            explanation="tie <b>& explanation",
            remediation="manual review",
            evidence="tie evidence",
        ),
        _finding(
            policy_id="M-POLICY",
            status=FindingStatus.FAIL,
            severity=Severity.MEDIUM,
            file="dags/m.py",
            start_line=20,
            fingerprint="fp-m-fail",
            explanation="medium <m>& explanation",
            remediation="review medium finding",
            evidence="medium evidence",
        ),
    ]
    return ScanReport(
        complete=True,
        result_fingerprint="seed-result-fingerprint",
        files_scanned=[Path("dags/z.py"), Path("dags/a.py"), Path("dags/b.py")],
        policies_evaluated=["Z-POLICY", "A-POLICY", "B-POLICY"],
        policies_skipped=["Z-SKIPPED", "A-SKIPPED"],
        findings=findings,
        runtime_observations=[
            RuntimeObservation(
                status=FindingStatus.FAIL,
                policy_id="Z-RUNTIME",
                message="runtime z",
                payload={"z": 2},
            ),
            RuntimeObservation(
                status=FindingStatus.PASS,
                policy_id="A-RUNTIME",
                payload={"a": 1},
            ),
        ],
        issues=[
            RunIssue(code="Z-ISSUE", message="z issue", path=Path("dags/z.py"), phase="runtime"),
            RunIssue(code="A-ISSUE", message="a issue", path=Path("dags/a.py"), phase="discovery"),
        ],
        gate_result=GateResult(
            gate_id="fixture-gate",
            passed=False,
            rules=[
                GateRuleResult(
                    rule_type="max-findings",
                    passed=False,
                    detail="fixture gate failed",
                    matching_findings=3,
                )
            ],
        ),
        run=RunMetadata(
            tool_version="fixture-tool-1.0",
            repository_revision="revision-excluded-from-fingerprint",
            input_hashes={"dags/z.py": "hash-z", "dags/a.py": "hash-a"},
            policy_pack_id="fixture-pack",
            policy_pack_version="2.0",
            runtime_image_digest="sha256:fixture-image",
            semantic_provider="fixture-provider",
            semantic_model="fixture-model",
            prompt_hashes={"Z-POLICY": "prompt-z", "A-POLICY": "prompt-a"},
            resolved_configuration={"z": "configuration"},
            environment={"FIXTURE_ENV": "value"},
            timestamp=FIXED_TIMESTAMP,
        ),
    )
