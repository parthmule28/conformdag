"""Direct characterization tests for Airflow safety evaluators."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from conformdag.analysis import SourceFile, analyze_source
from conformdag.checks.airflow.safety import ForbiddenOperatorEvaluator, RuffAirEvaluator, TopLevelIOEvaluator
from conformdag.checks.common import EvaluationContext
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
    Severity,
)
from conformdag.policy import load_policy_pack


def _model(source: str, relative_path: str = "dag.py"):
    source_file = SourceFile(Path(relative_path), relative_path, source, "input-hash")
    model, issue = analyze_source(source_file)
    assert issue is None
    assert model is not None
    return model


def _ruff_policy() -> Policy:
    return Policy.model_construct(
        id="AIR-TST-002",
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
        configuration=SimpleNamespace(kind="ruff-air", rules=["AIR002"]),
    )


def test_top_level_io_evaluator_is_directly_owned_by_safety_module() -> None:
    model = _model("import requests\nresult = requests.get('https://example.test')\n")
    pack = load_policy_pack(Path("policies/pack.yaml"), Path.cwd())
    policy = next(item for item in pack.policies if item.id == "AIR-DET-005")

    findings = TopLevelIOEvaluator().evaluate(EvaluationContext(policy, [model]))

    assert findings


@pytest.mark.parametrize(
    ("minimum", "maximum", "expected_match"),
    (("3.3.0", None, True), ("3.4.0", None, False), (None, "3.2.0", False), (None, "3.3.0", True)),
)
def test_forbidden_operator_respects_airflow_version_bounds(
    minimum: str | None,
    maximum: str | None,
    expected_match: bool,
) -> None:
    model = _model("from airflow.operators.python import PythonOperator\ntask = PythonOperator(task_id='task')\n")
    pack = load_policy_pack(Path("policies/pack.yaml"), Path.cwd())
    original = next(item for item in pack.policies if item.id == "AIR-DET-006")
    policy = original.model_copy(
        update={
            "configuration": ForbiddenOperatorsConfig(
                operators={
                    "airflow.operators.python.PythonOperator": OperatorRule(
                        replacement="use-taskflow",
                        min_airflow_version=minimum,
                        max_airflow_version=maximum,
                    )
                }
            )
        }
    )

    findings = ForbiddenOperatorEvaluator().evaluate(EvaluationContext(policy, [model], AirflowProfile.AIRFLOW_3_3_0))

    assert bool(findings) is expected_match
    if expected_match:
        assert findings[0].status is FindingStatus.FAIL


def test_ruff_evaluator_uses_safety_module_patch_seam(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = _model("from airflow import DAG\ndag = DAG(dag_id='x')\n", "dags/dag.py")
    violations: list[dict[str, Any]] = [
        {
            "filename": str(tmp_path / "dags/dag.py"),
            "location": {"row": 2, "column": 7},
            "code": "AIR002",
            "message": "DAG lacks a schedule argument",
        }
    ]

    def fake_run_ruff(*_args: object) -> list[dict[str, Any]]:
        return violations

    monkeypatch.setattr("conformdag.checks.airflow.safety.run_ruff", fake_run_ruff)

    findings = RuffAirEvaluator().evaluate(EvaluationContext(_ruff_policy(), [model], repository_root=tmp_path))

    assert len(findings) == 1
    assert findings[0].location.start_line == 2


def test_ruff_evaluator_returns_no_findings_when_fallback_has_no_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = _model("from airflow import DAG\ndag = DAG(dag_id='x')\n")

    def fake_run_ruff(*_args: object) -> None:
        return None

    monkeypatch.setattr("conformdag.checks.airflow.safety.run_ruff", fake_run_ruff)

    findings = RuffAirEvaluator().evaluate(EvaluationContext(_ruff_policy(), [model], repository_root=tmp_path))

    assert findings == []
