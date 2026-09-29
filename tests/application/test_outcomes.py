"""Transport-independent classification of canonical scan reports."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from conformdag.application import ExecutionOutcome, classify_report
from conformdag.models import (
    EnforcementType,
    Finding,
    FindingLocation,
    FindingStatus,
    GateResult,
    RunIssue,
    RunMetadata,
    RuntimeObservation,
    ScanReport,
    Severity,
)


def _report() -> ScanReport:
    return ScanReport(
        complete=True,
        result_fingerprint="f" * 64,
        run=RunMetadata(
            tool_version="0", policy_pack_id="x", policy_pack_version="1", timestamp=datetime(2026, 1, 1, tzinfo=UTC)
        ),
    )


def _finding(*, suppressed: bool = False, enforcement: EnforcementType = EnforcementType.DETERMINISTIC) -> Finding:
    return Finding(
        policy_id="P",
        policy_version="1",
        status=FindingStatus.FAIL,
        severity=Severity.HIGH,
        enforcement=enforcement,
        location=FindingLocation(file=Path("dags/a.py"), start_line=1),
        fingerprint="finding",
        suppressed=suppressed,
    )


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, ExecutionOutcome.SUCCESS),
        ({"gate_result": GateResult(gate_id="g", passed=False, rules=[])}, ExecutionOutcome.POLICY_FAILURE),
        (
            {"gate_result": GateResult(gate_id="g", passed=True, rules=[]), "findings": [_finding()]},
            ExecutionOutcome.SUCCESS,
        ),
        (
            {
                "gate_result": GateResult(gate_id="g", passed=True, rules=[]),
                "runtime_observations": [RuntimeObservation(status=FindingStatus.FAIL, policy_id="P")],
            },
            ExecutionOutcome.POLICY_FAILURE,
        ),
        ({"findings": [_finding()]}, ExecutionOutcome.POLICY_FAILURE),
        ({"findings": [_finding(suppressed=True)]}, ExecutionOutcome.SUCCESS),
        ({"findings": [_finding(enforcement=EnforcementType.SEMANTIC)]}, ExecutionOutcome.SUCCESS),
        (
            {"runtime_observations": [RuntimeObservation(status=FindingStatus.FAIL, policy_id="P")]},
            ExecutionOutcome.POLICY_FAILURE,
        ),
        ({"complete": False}, ExecutionOutcome.INCOMPLETE),
        (
            {"issues": [RunIssue(code="FATAL", message="broken", phase="discovery", fatal=True)]},
            ExecutionOutcome.INCOMPLETE,
        ),
    ],
)
def test_classify_report(changes: dict[str, object], expected: ExecutionOutcome) -> None:
    report = _report().model_copy(update=changes)
    assert classify_report(report) is expected
    assert classify_report(ScanReport.model_validate_json(report.model_dump_json())) is expected


def test_outcomes_are_public_application_contracts() -> None:
    from conformdag.application import __all__

    assert "ExecutionOutcome" in __all__
    assert "classify_report" in __all__
    assert ExecutionOutcome.SUCCESS.value == "success"
    assert ExecutionOutcome.POLICY_FAILURE.value == "policy_failure"
    assert ExecutionOutcome.INCOMPLETE.value == "incomplete"
