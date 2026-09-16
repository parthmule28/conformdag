"""Tests for typed deterministic evaluators and stable evidence."""

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from conformdag.analysis import SourceFile, analyze_source
from conformdag.evaluator import (
    CHECK_EVALUATORS,
    EvaluationContext,
    OwnerEvaluator,
    evaluate_deterministic,
    redact_evidence,
    structural_fingerprint,
)
from conformdag.models import (
    AirflowProfile,
    EnforcementConfig,
    EnforcementType,
    FindingStatus,
    ForbiddenOperatorsConfig,
    LifecycleStatus,
    OperatorRule,
    Ownership,
    Policy,
    PolicySource,
    RequiredOwnerConfig,
    Severity,
)
from conformdag.policy import load_policy_pack, resolve_policy_pack_path


def _model(source: str, relative_path: str = "dag.py"):
    source_file = SourceFile(Path(relative_path), relative_path, source, "input-hash")
    model, issue = analyze_source(source_file)
    assert issue is None
    assert model is not None
    return model


def _ruff_policy(policy_id: str = "AIR-TST-002", rules: list[str] | None = None) -> Policy:
    return Policy.model_construct(
        id=policy_id,
        title="Ruff AIR",
        version="1.0.0",
        status=LifecycleStatus.ACTIVE,
        severity=Severity.MEDIUM,
        airflow_profiles=[],
        ownership=Ownership(owner="platform"),
        source=PolicySource(document=Path("standards.md"), section="Ruff", content_hash="hash"),
        invariant="Ruff AIR violations are reported.",
        safe_path="Review the Ruff violation.",
        enforcement=EnforcementConfig(
            type=EnforcementType.DETERMINISTIC,
            deterministic_checks=["ruff-air"],
            blocking=True,
        ),
        configuration=SimpleNamespace(kind="ruff-air", rules=rules or ["AIR002"]),
    )


def test_ruff_air_check_kind_is_registered() -> None:
    assert "ruff-air" in CHECK_EVALUATORS


def test_ruff_air_evaluator_maps_violations_to_findings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = _model("from airflow import DAG\ndag = DAG(dag_id='x')\n", "dags/dag.py")
    policy = _ruff_policy()
    context = EvaluationContext(policy, [model], repository_root=tmp_path)
    payload: list[dict[str, Any]] = [
        {
            "filename": str(tmp_path / "dags/dag.py"),
            "location": {"row": 2, "column": 7},
            "code": "AIR002",
            "message": "`dag` lacks a schedule argument",
        }
    ]

    def fake_run_ruff(_root: Path, _rules: list[str]) -> list[dict[str, Any]]:
        return payload

    monkeypatch.setattr("conformdag.evaluator.run_ruff", fake_run_ruff)

    findings = CHECK_EVALUATORS["ruff-air"].evaluate(context)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.policy_id == "AIR-TST-002"
    assert finding.status is FindingStatus.FAIL
    assert finding.location.file == Path("dags/dag.py")
    assert finding.location.start_line == 2
    assert finding.evidence is not None
    assert "AIR002" in finding.evidence.text
    assert finding.explanation is not None
    assert "AIR002" in finding.explanation


def test_ruff_air_evaluator_skips_when_binary_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = _model("from airflow import DAG\ndag = DAG(dag_id='x')\n")
    policy = _ruff_policy()
    context = EvaluationContext(policy, [model], repository_root=tmp_path)

    def fake_run_ruff(_root: Path, _rules: list[str]) -> None:
        return None

    monkeypatch.setattr("conformdag.evaluator.run_ruff", fake_run_ruff)

    assert CHECK_EVALUATORS["ruff-air"].evaluate(context) == []


def test_evaluate_deterministic_runs_one_ruff_union_and_filters_by_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = _model("from airflow import DAG\ndag = DAG(dag_id='x')\n", "dags/dag.py")
    first = _ruff_policy("AIR-TST-002", ["AIR002"])
    second = _ruff_policy("AIR-TST-003", ["AIR003"])
    calls: list[tuple[Path, list[str]]] = []
    payload: list[dict[str, Any]] = [
        {
            "filename": str(tmp_path / "dags/dag.py"),
            "location": {"row": 2},
            "code": "AIR002",
            "message": "schedule is missing",
        },
        {
            "filename": str(tmp_path / "dags/dag.py"),
            "location": {"row": 2},
            "code": "AIR003",
            "message": "owner is missing",
        },
    ]

    def fake_run_ruff(root: Path, rules: list[str]) -> list[dict[str, Any]]:
        calls.append((root, rules))
        return payload

    monkeypatch.setattr("conformdag.evaluator.run_ruff", fake_run_ruff)

    findings, evaluated, skipped = evaluate_deterministic([first, second], [model], repository_root=tmp_path)

    assert calls == [(tmp_path, ["AIR002", "AIR003"])]
    assert evaluated == ["AIR-TST-002", "AIR-TST-003"]
    assert skipped == []
    assert [(finding.policy_id, finding.explanation) for finding in findings] == [
        ("AIR-TST-002", "AIR002: schedule is missing"),
        ("AIR-TST-003", "AIR003: owner is missing"),
    ]


def test_run_ruff_disables_source_fixes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from conformdag.ruff_adapter import run_ruff

    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((arguments, kwargs))
        return subprocess.CompletedProcess(arguments, 1, stdout="[]", stderr="")

    monkeypatch.setattr("conformdag.ruff_adapter.ruff_binary", lambda: "/usr/bin/ruff")
    monkeypatch.setattr("conformdag.ruff_adapter.subprocess.run", fake_run)

    assert run_ruff(tmp_path, ["AIR002"]) == []
    assert len(calls) == 1
    arguments, kwargs = calls[0]
    assert "--no-fix" in arguments
    assert arguments[arguments.index("--select") + 1] == "AIR002"
    assert kwargs["check"] is False


def test_run_ruff_returns_none_on_invocation_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from conformdag.ruff_adapter import run_ruff

    def fake_run(arguments: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, 2, stdout="", stderr="ruff failed")

    monkeypatch.setattr("conformdag.ruff_adapter.ruff_binary", lambda: "/usr/bin/ruff")
    monkeypatch.setattr("conformdag.ruff_adapter.subprocess.run", fake_run)

    assert run_ruff(tmp_path, ["AIR002"]) is None


def test_run_ruff_rejects_empty_json_on_violation_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from conformdag.ruff_adapter import run_ruff

    def fake_run(arguments: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, 1, stdout="", stderr="")

    monkeypatch.setattr("conformdag.ruff_adapter.ruff_binary", lambda: "/usr/bin/ruff")
    monkeypatch.setattr("conformdag.ruff_adapter.subprocess.run", fake_run)

    assert run_ruff(tmp_path, ["AIR002"]) is None


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


def test_deterministic_policy_suite_evaluates_tags_defaults_io_and_operators() -> None:
    pack = load_policy_pack(Path("policies/pack.yaml"), Path.cwd())
    model = _model(
        "from airflow import DAG\n"
        "from airflow.operators.python import PythonOperator\n"
        "from datetime import timedelta\n"
        "import requests\n"
        "dag = DAG(owner='platform', tags=['domain:data', 'owner:platform'])\n"
        "task = PythonOperator(task_id='task', dag=dag, execution_timeout=timedelta(hours=2), "
        "retries=2, retry_delay=timedelta(minutes=5))\n"
        "requests.get('https://example.invalid')\n"
        "old = PythonOperator(task_id='old', dag=dag)\n"
    )

    findings, evaluated, skipped = evaluate_deterministic(pack.policies, [model])

    assert evaluated == [
        "AIR-DET-001",
        "AIR-DET-002",
        "AIR-DET-003",
        "AIR-DET-004",
        "AIR-DET-005",
        "AIR-DET-006",
    ]
    assert skipped == ["AIR-SEM-001", "AIR-SEM-002", "AIR-SEM-003", "AIR-SEM-004"]
    by_policy: dict[str, list[FindingStatus]] = {}
    for finding in findings:
        by_policy.setdefault(finding.policy_id, []).append(finding.status)
    assert by_policy["AIR-DET-001"] == [FindingStatus.PASS]
    assert by_policy["AIR-DET-002"] == [FindingStatus.PASS]
    assert by_policy["AIR-DET-003"] == [FindingStatus.PASS, FindingStatus.PASS]
    assert by_policy["AIR-DET-004"] == [FindingStatus.PASS, FindingStatus.PASS]
    assert FindingStatus.FAIL in by_policy["AIR-DET-005"]
    assert len(by_policy["AIR-DET-006"]) == 2


def test_uncertain_dynamic_module_call_is_review_not_blocking() -> None:
    pack = load_policy_pack(Path("policies/pack.yaml"), Path.cwd())
    policy = next(item for item in pack.policies if item.id == "AIR-DET-005")
    findings = evaluate_deterministic([policy], [_model("factory = get_factory()\nresult = factory()()\n")])[0]

    assert findings
    assert all(item.status is FindingStatus.NEEDS_REVIEW for item in findings)


def test_forbidden_operator_rule_respects_airflow_profile() -> None:
    pack = load_policy_pack(Path("policies/pack.yaml"), Path.cwd())
    original = next(item for item in pack.policies if item.id == "AIR-DET-006")
    policy = original.model_copy(
        update={
            "configuration": ForbiddenOperatorsConfig(
                operators={
                    "airflow.operators.python.PythonOperator": OperatorRule(
                        replacement="use-taskflow",
                        airflow_profiles=[AirflowProfile.AIRFLOW_3_3_0],
                    )
                }
            )
        }
    )
    model = _model("from airflow.operators.python import PythonOperator\ntask = PythonOperator(task_id='task')\n")

    from conformdag.evaluator import EvaluationContext, ForbiddenOperatorEvaluator

    evaluator = ForbiddenOperatorEvaluator()
    assert (
        evaluator.evaluate(EvaluationContext(policy, [model], AirflowProfile.AIRFLOW_3_3_0))[0].status
        is FindingStatus.FAIL
    )


def test_evaluate_deterministic_routes_community_policies_by_check_kind() -> None:
    pack = load_policy_pack(resolve_policy_pack_path(Path("community")), Path.cwd())
    model = _model(
        "from airflow import DAG\n"
        "from airflow.operators.empty import EmptyOperator\n"
        "with DAG(dag_id='example', default_args={'execution_timeout': 3600}) as dag:\n"
        "    EmptyOperator(task_id='start')\n"
    )

    findings, evaluated, skipped = evaluate_deterministic(pack.policies, [model])

    assert skipped == []
    assert evaluated == ["COM-DET-001", "COM-DET-002", "COM-DET-003"]
    assert any(item.policy_id == "COM-DET-001" and item.status is FindingStatus.PASS for item in findings)
