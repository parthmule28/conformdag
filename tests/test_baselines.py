"""Contract tests for immutable baseline identity values."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from conformdag.baselines import Baseline, baseline_from_fingerprints, baseline_from_report
from conformdag.models import EnforcementType, Finding, FindingStatus, RunMetadata, ScanReport, Severity


def _finding(fingerprint: str, *, suppressed: bool = False) -> Finding:
    return Finding(
        policy_id="AIR-DET-001",
        policy_version="1.0.0",
        status=FindingStatus.FAIL,
        severity=Severity.HIGH,
        enforcement=EnforcementType.DETERMINISTIC,
        fingerprint=fingerprint,
        suppressed=suppressed,
    )


def _report(*findings: Finding) -> ScanReport:
    return ScanReport(
        complete=True,
        result_fingerprint="report-fingerprint",
        findings=list(findings),
        run=RunMetadata(
            tool_version="test",
            policy_pack_id="test-pack",
            policy_pack_version="1",
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )


def test_baseline_is_frozen_and_uses_frozenset() -> None:
    baseline = Baseline(fingerprints=frozenset({"known"}))

    assert isinstance(baseline.fingerprints, frozenset)
    field_name = "fingerprints"
    with pytest.raises(FrozenInstanceError):
        setattr(baseline, field_name, frozenset({"changed"}))


def test_baseline_from_report_includes_all_findings_including_suppressed() -> None:
    report = _report(_finding("active"), _finding("historically-suppressed", suppressed=True))

    baseline = baseline_from_report(report)

    assert baseline.fingerprints == frozenset({"active", "historically-suppressed"})


def test_baseline_from_fingerprints_snapshots_iterable() -> None:
    source = ["first", "second"]
    fingerprints = (fingerprint for fingerprint in source)

    baseline = baseline_from_fingerprints(fingerprints)
    source.append("added-later")

    assert baseline.fingerprints == frozenset({"first", "second"})


def test_empty_baseline_is_a_value_distinct_from_none() -> None:
    baseline = baseline_from_fingerprints(())

    assert baseline is not None
    assert baseline.fingerprints == frozenset()
