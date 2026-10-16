"""Compatibility tests for canonical scan report fingerprints."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conformdag.models import (
    Confidence,
    EnforcementConfig,
    EnforcementType,
    FindingStatus,
    Policy,
    ScanReport,
    SemanticAuditEvidence,
    SemanticResponse,
    SemanticRunMetadata,
    Severity,
)
from conformdag.reporting import apply_suppressions, normalize_report
from conformdag.semantic import SemanticContext
from conformdag.semantic_evaluator import semantic_finding
from reporting.fixtures import fixed_report, fixed_suppression
from reporting.test_normalize_contract import EXPECTED_FINGERPRINT, EXPECTED_NORMALIZED_JSON


def _fingerprint(report: ScanReport) -> str:
    return normalize_report(report).result_fingerprint


def _with_finding(report: ScanReport, index: int, **updates: object) -> ScanReport:
    findings = list(report.findings)
    findings[index] = findings[index].model_copy(update=updates)
    return report.model_copy(update={"findings": findings})


def _semantic_finding(explanation: str):
    policy = Policy.model_construct(
        id="C19-SEM-REPORT",
        version="1.0.0",
        severity=Severity.MEDIUM,
        safe_path="Review the semantic fixture.",
        enforcement=EnforcementConfig(type=EnforcementType.SEMANTIC, blocking=True),
    )
    response = SemanticResponse(
        status="FAIL",
        evidence="bounded evidence",
        explanation=explanation,
        remediation="same remediation",
        confidence=Confidence.HIGH,
        audit_evidence=[
            SemanticAuditEvidence(
                criterion="retry-safety",
                source_type="source",
                location="dags/sample.py",
                excerpt="same citation excerpt",
            )
        ],
    )
    context = SemanticContext(
        "[SOURCE dags/sample.py]\noperation()",
        "fixed-context-hash",
        ("dags/sample.py",),
        (),
    )
    return semantic_finding(policy, response, context, Path("dags/sample.py"))


def test_report_contract_retains_c18_frozen_fingerprint_and_normalized_json() -> None:
    normalized = normalize_report(fixed_report())

    assert normalized.result_fingerprint == EXPECTED_FINGERPRINT
    assert normalized.result_fingerprint == "8050ab09ad677b729bc5287e99347713afc10bf0d87957066b1494442f034e26"
    assert normalized.model_dump(mode="json") == json.loads(EXPECTED_NORMALIZED_JSON)


@pytest.mark.parametrize(
    ("run_updates",),
    [
        ({"tool_version": "different-tool"},),
        ({"repository_revision": "different-revision"},),
        ({"resolved_configuration": {"changed": "configuration"}},),
        ({"environment": {"CHANGED_ENV": "value"}},),
        (
            {
                "semantic_runs": [
                    SemanticRunMetadata(
                        policy_id="C19-SEM-001",
                        requested_model="different-model",
                        context_hash="diagnostic-context",
                        prompt_hash="diagnostic-prompt",
                        latency_ms=42,
                    )
                ]
            },
        ),
    ],
    ids=("tool-version", "repository-revision", "resolved-configuration", "environment", "semantic-runs"),
)
def test_excluded_run_metadata_does_not_change_report_fingerprint(run_updates: dict[str, object]) -> None:
    report = fixed_report()
    changed_run = report.run.model_copy(update=run_updates)
    changed = report.model_copy(update={"run": changed_run})

    assert _fingerprint(changed) == _fingerprint(report)


def test_report_fingerprint_is_independent_of_ordered_collections_and_mappings() -> None:
    report = fixed_report()
    changed = report.model_copy(
        update={
            "findings": list(reversed(report.findings)),
            "issues": list(reversed(report.issues)),
            "files_scanned": list(reversed(report.files_scanned)),
            "runtime_observations": list(reversed(report.runtime_observations)),
            "policies_evaluated": list(reversed(report.policies_evaluated)),
            "policies_skipped": list(reversed(report.policies_skipped)),
            "run": report.run.model_copy(
                update={
                    "input_hashes": dict(reversed(list(report.run.input_hashes.items()))),
                    "prompt_hashes": dict(reversed(list(report.run.prompt_hashes.items()))),
                }
            ),
        }
    )

    assert _fingerprint(changed) == _fingerprint(report)


def test_finding_status_changes_report_fingerprint() -> None:
    report = fixed_report()
    changed = _with_finding(report, 0, status=FindingStatus.PASS)

    assert changed.findings[0].status is FindingStatus.PASS
    assert _fingerprint(changed) != _fingerprint(report)


def test_finding_explanation_changes_report_fingerprint() -> None:
    report = fixed_report()
    changed = _with_finding(report, 0, explanation="different serialized explanation")

    assert _fingerprint(changed) != _fingerprint(report)


def test_finding_evidence_changes_report_fingerprint() -> None:
    report = fixed_report()
    finding = report.findings[0]
    assert finding.evidence is not None
    changed = _with_finding(report, 0, evidence=finding.evidence.model_copy(update={"text": "different evidence"}))

    assert _fingerprint(changed) != _fingerprint(report)


def test_suppression_provenance_changes_report_fingerprint() -> None:
    report = fixed_report()
    finding_index = next(index for index, finding in enumerate(report.findings) if finding.suppression is not None)
    suppression = report.findings[finding_index].suppression
    assert suppression is not None
    changed = _with_finding(
        report,
        finding_index,
        suppression=suppression.model_copy(update={"reason": "updated exception rationale"}),
    )

    assert _fingerprint(changed) != _fingerprint(report)


def test_issue_message_changes_report_fingerprint() -> None:
    report = fixed_report()
    issues = list(report.issues)
    issues[0] = issues[0].model_copy(update={"message": "changed issue message"})
    changed = report.model_copy(update={"issues": issues})

    assert _fingerprint(changed) != _fingerprint(report)


def test_runtime_observation_changes_report_fingerprint() -> None:
    report = fixed_report()
    observations = list(report.runtime_observations)
    observations[0] = observations[0].model_copy(update={"message": "changed runtime observation"})
    changed = report.model_copy(update={"runtime_observations": observations})

    assert _fingerprint(changed) != _fingerprint(report)


def test_input_hash_changes_report_fingerprint() -> None:
    report = fixed_report()
    input_hashes = dict(report.run.input_hashes)
    input_hashes["dags/a.py"] = "changed-source-hash"
    changed = report.model_copy(update={"run": report.run.model_copy(update={"input_hashes": input_hashes})})

    assert _fingerprint(changed) != _fingerprint(report)


def test_semantic_prose_can_leave_finding_identity_stable_but_change_report_identity() -> None:
    report = fixed_report()
    first_semantic = _semantic_finding("provider explanation one")
    second_semantic = _semantic_finding("provider explanation two")
    assert first_semantic.fingerprint == second_semantic.fingerprint
    first_report = report.model_copy(update={"findings": [*report.findings, first_semantic]})
    second_report = report.model_copy(update={"findings": [*report.findings, second_semantic]})

    assert _fingerprint(first_report) != _fingerprint(second_report)


def test_applying_suppression_keeps_finding_fingerprint_and_changes_report_identity() -> None:
    report = fixed_report()
    target = next(finding for finding in report.findings if finding.fingerprint == "fp-b-tie")
    suppression = fixed_suppression().model_copy(
        update={"policy_id": target.policy_id, "fingerprint": target.fingerprint}
    )
    suppressed_findings, issues = apply_suppressions(
        report.findings,
        [suppression],
        now=datetime(2026, 6, 1, tzinfo=UTC),
    )
    suppressed_target = next(finding for finding in suppressed_findings if finding.fingerprint == target.fingerprint)
    changed = report.model_copy(update={"findings": suppressed_findings})

    assert issues == []
    assert suppressed_target.suppressed is True
    assert suppressed_target.fingerprint == target.fingerprint
    assert _fingerprint(changed) != _fingerprint(report)


def test_normalize_report_does_not_mutate_input_and_preserves_report_version_and_schema() -> None:
    report = fixed_report()
    before = report.model_dump(mode="json")

    normalized = normalize_report(report)

    assert report.model_dump(mode="json") == before
    assert normalized is not report
    assert report.report_version == normalized.report_version == "2"
    assert json.loads(Path("schemas/scan-report.json").read_text(encoding="utf-8")) == ScanReport.model_json_schema()
