"""Tests for suppression matching and canonical report normalization."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from conformdag.analysis import SourceFile, analyze_source
from conformdag.evaluator import EvaluationContext, OwnerEvaluator
from conformdag.models import RunMetadata, ScanReport, Suppression
from conformdag.policy import load_policy_pack
from conformdag.reporting import apply_suppressions, has_blocking_failures


def _finding():
    pack = load_policy_pack(Path("policies/pack.yaml"), Path.cwd())
    policy = next(item for item in pack.policies if item.id == "AIR-DET-001")
    source = SourceFile(
        Path("dag.py"), "dag.py", "from airflow import DAG\nDAG(owner='bad')\n", "hash"
    )
    model, issue = analyze_source(source)
    assert issue is None
    assert model is not None
    return OwnerEvaluator().evaluate(EvaluationContext(policy, [model]))[0]


def _suppression(fingerprint: str, expires_at: datetime) -> Suppression:
    return Suppression(
        fingerprint=fingerprint,
        policy_id="AIR-DET-001",
        reason="tracked migration",
        owner="platform",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        expires_at=expires_at,
    )


def test_applies_nonexpired_suppression_and_removes_blocking_exit() -> None:
    finding = _finding()
    current = datetime(2026, 7, 30, tzinfo=UTC)

    findings, issues = apply_suppressions(
        [finding], [_suppression(finding.fingerprint, current + timedelta(days=1))], current
    )

    assert findings[0].suppressed is True
    assert issues == []
    report = ScanReport(
        complete=True,
        result_fingerprint="result",
        findings=findings,
        run=RunMetadata(
            tool_version="test",
            policy_pack_id="default",
            policy_pack_version="1",
            timestamp=current,
        ),
    )
    assert has_blocking_failures(report) is False


def test_expired_and_unmatched_suppressions_are_diagnostic() -> None:
    finding = _finding()
    current = datetime(2026, 7, 30, tzinfo=UTC)

    findings, issues = apply_suppressions(
        [finding],
        [
            _suppression(finding.fingerprint, current - timedelta(days=1)),
            _suppression("missing-fingerprint", current + timedelta(days=1)),
        ],
        current,
    )

    assert findings[0].suppressed is False
    assert {issue.code for issue in issues} == {"SUPPRESSION_EXPIRED", "SUPPRESSION_UNMATCHED"}
