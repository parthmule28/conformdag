"""Tests for suppression matching and canonical report normalization."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from conformdag.analysis import SourceFile, analyze_source
from conformdag.evaluator import EvaluationContext, OwnerEvaluator
from conformdag.models import EnforcementType, RunMetadata, ScanReport, Suppression
from conformdag.policy import load_policy_pack
from conformdag.reporting import (
    apply_suppressions,
    has_blocking_failures,
    render_html,
    render_sarif,
)


def _finding():
    pack = load_policy_pack(Path("policies/pack.yaml"), Path.cwd())
    policy = next(item for item in pack.policies if item.id == "AIR-DET-001")
    source = SourceFile(Path("dag.py"), "dag.py", "from airflow import DAG\nDAG(owner='bad')\n", "hash")
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


def test_sarif_and_html_render_from_the_same_canonical_finding() -> None:
    finding = _finding()
    current = datetime(2026, 7, 30, tzinfo=UTC)
    report = ScanReport(
        complete=True,
        result_fingerprint="result",
        findings=[finding],
        run=RunMetadata(
            tool_version="test",
            policy_pack_id="default",
            policy_pack_version="1",
            timestamp=current,
        ),
    )

    sarif = render_sarif(report)
    html = render_html(report, include_evidence=False)

    assert sarif["version"] == "2.1.0"
    runs = cast(list[dict[str, object]], sarif["runs"])
    run = runs[0]
    results = cast(list[dict[str, object]], run["results"])
    assert results[0]["ruleId"] == "AIR-DET-001"
    assert '<html lang="en">' in html
    assert "DAG owner=" not in html
    assert '<th scope="col">Policy</th>' in html


def test_explicitly_blocking_semantic_failure_blocks() -> None:
    finding = _finding().model_copy(update={"enforcement": EnforcementType.SEMANTIC, "blocking": True})
    report = ScanReport(
        complete=True,
        result_fingerprint="result",
        findings=[finding],
        run=RunMetadata(
            tool_version="test",
            policy_pack_id="default",
            policy_pack_version="1",
            timestamp=datetime(2026, 7, 30, tzinfo=UTC),
        ),
    )

    assert has_blocking_failures(report) is True
