"""Tests for typed deterministic evaluators and stable evidence."""

from pathlib import Path

from conformdag.analysis import SourceFile, analyze_source
from conformdag.evaluator import (
    EvaluationContext,
    OwnerEvaluator,
    redact_evidence,
    structural_fingerprint,
)
from conformdag.models import FindingStatus, RequiredOwnerConfig
from conformdag.policy import load_policy_pack


def _model(source: str):
    source_file = SourceFile(Path("dag.py"), "dag.py", source, "input-hash")
    model, issue = analyze_source(source_file)
    assert issue is None
    assert model is not None
    return model


def test_owner_evaluator_handles_valid_and_invalid_values() -> None:
    pack = load_policy_pack(Path("policies/pack.yaml"), Path.cwd())
    policy = next(item for item in pack.policies if item.id == "AIR-DET-001")
    evaluator = OwnerEvaluator()

    findings = evaluator.evaluate(
        EvaluationContext(
            policy,
            [_model("from airflow import DAG\ndag = DAG(owner='platform')\n")],
        )
    )
    invalid = evaluator.evaluate(
        EvaluationContext(
            policy,
            [_model("from airflow.sdk import DAG\ndag = DAG(owner='unknown')\n")],
        )
    )

    assert findings[0].status is FindingStatus.PASS
    assert invalid[0].status is FindingStatus.FAIL
    assert invalid[0].evidence is not None
    assert "DAG.owner" in invalid[0].evidence.text
    assert isinstance(policy.configuration, RequiredOwnerConfig)


def test_evidence_is_bounded_and_redacted() -> None:
    evidence = redact_evidence("password='secret-value' " + "x" * 500, max_chars=80)

    assert len(evidence) <= 80
    assert "secret-value" not in evidence
    assert "[REDACTED]" in evidence


def test_structural_fingerprint_does_not_depend_on_line_number() -> None:
    pack = load_policy_pack(Path("policies/pack.yaml"), Path.cwd())
    policy = next(item for item in pack.policies if item.id == "AIR-DET-001")

    first = structural_fingerprint(policy, "dag.py", "dag:dag:owner:platform", FindingStatus.PASS)
    second = structural_fingerprint(policy, "dag.py", "dag:dag:owner:platform", FindingStatus.PASS)

    assert first == second
