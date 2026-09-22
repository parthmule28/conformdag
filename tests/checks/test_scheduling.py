"""Direct characterization tests for Airflow scheduling evaluators."""

from pathlib import Path

from conformdag.analysis import SourceFile, analyze_source
from conformdag.checks.airflow.scheduling import RetryEvaluator, TimeoutEvaluator
from conformdag.checks.common import EvaluationContext
from conformdag.models import FindingStatus, Policy
from conformdag.policy import load_policy_pack


def _model(source: str):
    source_file = SourceFile(Path("dag.py"), "dag.py", source, "input-hash")
    model, issue = analyze_source(source_file)
    assert issue is None
    assert model is not None
    return model


def _policy(policy_id: str) -> Policy:
    pack = load_policy_pack(Path("policies/pack.yaml"), Path.cwd())
    return next(policy for policy in pack.policies if policy.id == policy_id)


def test_timeout_evaluator_is_directly_owned_by_scheduling_module() -> None:
    model = _model(
        "from airflow.operators.empty import EmptyOperator\n"
        "task = EmptyOperator(task_id='task', execution_timeout=3600)\n"
    )

    findings = TimeoutEvaluator().evaluate(EvaluationContext(_policy("AIR-DET-003"), [model]))

    assert findings[0].status is FindingStatus.PASS


def test_retry_evaluator_is_directly_owned_by_scheduling_module() -> None:
    model = _model(
        "from airflow.operators.empty import EmptyOperator\n"
        "task = EmptyOperator(task_id='task', retries=1, retry_delay=30)\n"
    )

    findings = RetryEvaluator().evaluate(EvaluationContext(_policy("AIR-DET-004"), [model]))

    assert findings[0].status is FindingStatus.PASS
