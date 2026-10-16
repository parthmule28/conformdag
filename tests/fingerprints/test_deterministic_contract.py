"""Compatibility tests for deterministic finding fingerprints."""

import hashlib
from pathlib import Path

import pytest

from conformdag.analysis import SourceFile, analyze_source
from conformdag.checks.common import finding as deterministic_finding
from conformdag.checks.common import structural_fingerprint
from conformdag.evaluator import structural_fingerprint as legacy_structural_fingerprint
from conformdag.models import FindingStatus, Policy, Severity


def _policy(policy_id: str = "C19-DET-001", version: str = "2.7.1") -> Policy:
    return Policy.model_construct(
        id=policy_id, version=version, severity=Severity.MEDIUM, safe_path="Review the fixture."
    )


def _model():
    source = SourceFile(
        Path("dags/sample.py"),
        "dags/sample.py",
        "from airflow import DAG\ndag = DAG(dag_id='sample')\n",
        "source-hash",
    )
    model, issue = analyze_source(source)
    assert issue is None
    assert model is not None
    return model


def test_structural_fingerprint_matches_independent_sha256_oracle_and_is_repeatable() -> None:
    policy = _policy()
    path = "dags/sample.py"
    anchor = "dag:sample:owner:platform"
    status = FindingStatus.FAIL
    expected = hashlib.sha256(b"C19-DET-001:2.7.1:dags/sample.py:dag:sample:owner:platform:FAIL").hexdigest()
    assert expected == "3281f0b888f5081eeb39cd711b3f57b6f300a5117746ddb16c000ace603d3036"

    first = structural_fingerprint(policy, path, anchor, status)
    second = structural_fingerprint(policy, path, anchor, status)

    assert first == expected
    assert second == expected


@pytest.mark.parametrize(
    ("changed_policy", "changed_path", "changed_anchor", "changed_status"),
    [
        (_policy(policy_id="C19-DET-002"), "dags/sample.py", "dag:sample:owner:platform", FindingStatus.FAIL),
        (_policy(version="2.7.2"), "dags/sample.py", "dag:sample:owner:platform", FindingStatus.FAIL),
        (_policy(), "dags/renamed.py", "dag:sample:owner:platform", FindingStatus.FAIL),
        (_policy(), "dags/sample.py", "dag:sample:owner:team", FindingStatus.FAIL),
        (_policy(), "dags/sample.py", "dag:sample:owner:platform", FindingStatus.PASS),
    ],
    ids=("policy-id", "policy-version", "path", "anchor", "status"),
)
def test_each_identity_input_individually_changes_the_fingerprint(
    changed_policy: Policy,
    changed_path: str,
    changed_anchor: str,
    changed_status: FindingStatus,
) -> None:
    baseline = structural_fingerprint(_policy(), "dags/sample.py", "dag:sample:owner:platform", FindingStatus.FAIL)

    changed = structural_fingerprint(changed_policy, changed_path, changed_anchor, changed_status)

    assert changed != baseline


def test_external_line_change_does_not_affect_fingerprint_when_anchor_is_unchanged() -> None:
    policy = _policy()
    anchor = "dag:sample:owner:platform"
    model = _model()

    first = deterministic_finding(policy, model, 12, FindingStatus.FAIL, "same evidence", anchor)
    shifted = deterministic_finding(policy, model, 120, FindingStatus.FAIL, "same evidence", anchor)

    assert first.location.start_line == 12
    assert shifted.location.start_line == 120
    assert first.fingerprint == shifted.fingerprint


def test_line_embedded_in_ruff_style_anchor_changes_fingerprint() -> None:
    policy = _policy()

    row_two = structural_fingerprint(policy, "dags/sample.py", "ruff:AIR002:2", FindingStatus.FAIL)
    row_three = structural_fingerprint(policy, "dags/sample.py", "ruff:AIR002:3", FindingStatus.FAIL)
    expected_row_two = hashlib.sha256(b"C19-DET-001:2.7.1:dags/sample.py:ruff:AIR002:2:FAIL").hexdigest()

    assert row_two == expected_row_two
    assert row_three != row_two


def test_evaluator_compatibility_import_is_the_canonical_helper() -> None:
    assert legacy_structural_fingerprint is structural_fingerprint
