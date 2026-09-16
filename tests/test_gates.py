"""Quality-gate evaluation: pure-function tests for every rule type."""

from datetime import UTC, datetime
from pathlib import Path

from conformdag.gates import blocking_findings, evaluate_gate, evaluate_pack_gates, validate_quality_gates
from conformdag.models import (
    EnforcementConfig,
    EnforcementType,
    Finding,
    FindingLocation,
    FindingStatus,
    LifecycleStatus,
    Ownership,
    Policy,
    PolicyPack,
    PolicySource,
    QualityGate,
    RequiredOwnerConfig,
    RunMetadata,
    ScanReport,
    Severity,
)


def _finding(policy_id: str, status: FindingStatus, fingerprint: str, *, suppressed: bool = False) -> Finding:
    return Finding(
        policy_id=policy_id,
        policy_version="1.0.0",
        status=status,
        severity=Severity.HIGH,
        enforcement=EnforcementType.DETERMINISTIC,
        location=FindingLocation(file=Path("dags/a.py"), start_line=1),
        fingerprint=fingerprint,
        suppressed=suppressed,
    )


def _report(*findings: Finding) -> ScanReport:
    return ScanReport(
        complete=True,
        result_fingerprint="f" * 64,
        findings=list(findings),
        run=RunMetadata(
            tool_version="0",
            policy_pack_id="x",
            policy_pack_version="1",
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )


def _pack(*gates: QualityGate) -> PolicyPack:
    return PolicyPack(schema_version="1", id="x", version="1", policies=[], quality_gates=list(gates))


def test_no_new_findings_rule_compares_fingerprints_against_baseline() -> None:
    gate = QualityGate.model_validate({"id": "g", "rules": [{"type": "no-new-findings"}]})
    baseline = _report(_finding("AIR-DET-001", FindingStatus.FAIL, "known"))
    current = _report(
        _finding("AIR-DET-001", FindingStatus.FAIL, "known"), _finding("AIR-DET-002", FindingStatus.FAIL, "brand-new")
    )
    result = evaluate_gate(gate, current, baseline)
    assert not result.passed
    rule = result.rules[0]
    assert rule.rule_type == "no-new-findings"
    assert rule.matching_findings == 1

    only_known = _report(_finding("AIR-DET-001", FindingStatus.FAIL, "known"))
    assert evaluate_gate(gate, only_known, baseline).passed


def test_max_severity_blocks_at_or_above_threshold() -> None:
    gate = QualityGate.model_validate({"id": "g", "rules": [{"type": "max-severity", "severity": "high"}]})
    critical = _finding("A", FindingStatus.FAIL, "f1").model_copy(update={"severity": Severity.CRITICAL})
    assert not evaluate_gate(gate, _report(critical), None).passed

    medium = _finding("A", FindingStatus.FAIL, "f1").model_copy(update={"severity": Severity.MEDIUM})
    assert evaluate_gate(gate, _report(medium), None).passed


def test_max_findings_fails_at_the_count() -> None:
    gate = QualityGate.model_validate({"id": "g", "rules": [{"type": "max-findings", "count": 2}]})
    two = _report(_finding("A", FindingStatus.FAIL, "f1"), _finding("B", FindingStatus.FAIL, "f2"))
    assert not evaluate_gate(gate, two, None).passed
    assert evaluate_gate(gate, _report(_finding("A", FindingStatus.FAIL, "f1")), None).passed


def test_always_block_lists_policy_ids() -> None:
    gate = QualityGate.model_validate({"id": "g", "rules": [{"type": "always-block", "policy_ids": ["AIR-DET-005"]}]})
    assert not evaluate_gate(gate, _report(_finding("AIR-DET-005", FindingStatus.FAIL, "f1")), None).passed
    assert evaluate_gate(gate, _report(_finding("AIR-DET-001", FindingStatus.FAIL, "f2")), None).passed


def test_failure_rate_uses_failing_over_total() -> None:
    gate = QualityGate.model_validate({"id": "g", "rules": [{"type": "failure-rate", "max_percent": 50.0}]})
    half = _report(
        _finding("A", FindingStatus.FAIL, "f1"),
        _finding("B", FindingStatus.PASS, "f2"),
    )
    assert not evaluate_gate(gate, half, None).passed

    clean = _report(_finding("B", FindingStatus.PASS, "f2"))
    assert evaluate_gate(gate, clean, None).passed
    assert evaluate_gate(gate, _report(), None).passed


def test_suppressed_findings_never_block() -> None:
    gate = QualityGate.model_validate({"id": "g", "rules": [{"type": "max-findings", "count": 0}]})
    report = _report(_finding("A", FindingStatus.FAIL, "f1", suppressed=True))
    assert blocking_findings(report) == []
    assert evaluate_gate(gate, report, None).passed


def test_all_gates_must_pass_and_first_failure_is_reported() -> None:
    pack = _pack(
        QualityGate.model_validate({"id": "ok", "rules": [{"type": "max-findings", "count": 0}]}),
        QualityGate.model_validate({"id": "strict", "rules": [{"type": "max-findings", "count": 1}]}),
    )
    result = evaluate_pack_gates(pack, _report(_finding("A", FindingStatus.FAIL, "f1")), None)
    assert result is not None
    assert result.gate_id == "ok"
    assert not result.passed


def test_pack_without_gates_evaluates_to_none() -> None:
    assert evaluate_pack_gates(_pack(), _report(), None) is None


def test_validate_quality_gates_rejects_duplicate_ids_and_unknown_policies() -> None:
    pack = _pack(
        QualityGate.model_validate({"id": "g", "rules": [{"type": "max-findings", "count": 1}]}),
        QualityGate.model_validate({"id": "g", "rules": [{"type": "max-findings", "count": 2}]}),
    )
    issues = validate_quality_gates(pack)
    assert any("unique" in issue for issue in issues)

    referencing = _pack(
        QualityGate.model_validate({"id": "g", "rules": [{"type": "always-block", "policy_ids": ["AIR-DET-999"]}]})
    )
    assert any("AIR-DET-999" in issue for issue in validate_quality_gates(referencing))


def test_validate_policy_pack_reports_unknown_check_and_unknown_gate() -> None:
    from conformdag.policy import validate_policy_pack

    policy = Policy(
        id="AIR-TST-100",
        title="Owner policy",
        version="1.0.0",
        status=LifecycleStatus.ACTIVE,
        severity=Severity.HIGH,
        airflow_profiles=[],
        ownership=Ownership(owner="platform"),
        source=PolicySource(document=Path("standards/dag-authoring.md"), section="x", content_hash="x"),
        invariant="Every DAG declares an owner.",
        enforcement=EnforcementConfig(type=EnforcementType.DETERMINISTIC, deterministic_checks=["missing-check"]),
        configuration=RequiredOwnerConfig(allowed_values=["platform"]),
    )
    pack = PolicyPack(
        schema_version="1",
        id="boundary",
        version="1",
        policies=[policy],
        quality_gates=[
            QualityGate.model_validate(
                {"id": "g", "rules": [{"type": "always-block", "policy_ids": ["AIR-MISSING-001"]}]}
            )
        ],
    )

    issues = validate_policy_pack(pack)

    assert any("unknown deterministic check" in issue for issue in issues)
    assert any("unknown policy ids" in issue for issue in issues)
