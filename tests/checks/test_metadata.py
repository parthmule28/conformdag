"""Direct characterization tests for Airflow metadata evaluators."""

from pathlib import Path

from conformdag.analysis import SourceFile, analyze_source
from conformdag.checks.airflow.metadata import OwnerEvaluator, TagEvaluator
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


def test_owner_evaluator_is_directly_owned_by_metadata_module() -> None:
    model = _model("from airflow import DAG\ndag = DAG(dag_id='x', owner='platform')\n")

    findings = OwnerEvaluator().evaluate(EvaluationContext(_policy("AIR-DET-001"), [model]))

    assert findings[0].status is FindingStatus.PASS


def test_tag_evaluator_is_directly_owned_by_metadata_module() -> None:
    model = _model(
        "from airflow import DAG\n"
        "dag = DAG(dag_id='x', tags=['domain:data', 'owner:platform'])\n"
    )

    findings = TagEvaluator().evaluate(EvaluationContext(_policy("AIR-DET-002"), [model]))

    assert findings[0].status is FindingStatus.PASS
