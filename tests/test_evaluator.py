"""Tests for typed deterministic evaluators and stable evidence."""

from pathlib import Path

from conformdag.analysis import SourceFile, analyze_source
from conformdag.evaluator import (
    EvaluationContext,
    OwnerEvaluator,
    evaluate_deterministic,
    redact_evidence,
    structural_fingerprint,
)
from conformdag.models import (
    AirflowProfile,
    FindingStatus,
    ForbiddenOperatorsConfig,
    OperatorRule,
    RequiredOwnerConfig,
)
from conformdag.policy import load_policy_pack, resolve_policy_pack_path


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
    findings = evaluate_deterministic(
        [policy], [_model("factory = get_factory()\nresult = factory()()\n")]
    )[0]

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
    model = _model(
        "from airflow.operators.python import PythonOperator\n"
        "task = PythonOperator(task_id='task')\n"
    )

    from conformdag.evaluator import EvaluationContext, ForbiddenOperatorEvaluator

    evaluator = ForbiddenOperatorEvaluator()
    assert (
        evaluator.evaluate(EvaluationContext(policy, [model], AirflowProfile.AIRFLOW_3_3_0))[
            0
        ].status
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
    assert any(
        item.policy_id == "COM-DET-001" and item.status is FindingStatus.PASS for item in findings
    )
