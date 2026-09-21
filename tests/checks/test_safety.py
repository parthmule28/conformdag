"""Direct characterization tests for Airflow safety evaluators."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from conformdag.analysis import SourceFile, analyze_source
from conformdag.checks.airflow.safety import RuffAirEvaluator, TopLevelIOEvaluator
from conformdag.checks.common import EvaluationContext
from conformdag.models import (
    EnforcementConfig,
    EnforcementType,
    LifecycleStatus,
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


def test_ruff_evaluator_uses_safety_module_patch_seam(tmp_path: Path, monkeypatch: Any) -> None:
    model = _model("from airflow import DAG\ndag = DAG(dag_id='x')\n", "dags/dag.py")
    violations: list[dict[str, Any]] = [
        {
            "filename": str(tmp_path / "dags/dag.py"),
            "location": {"row": 2, "column": 7},
            "code": "AIR002",
            "message": "DAG lacks a schedule argument",
        }
    ]
    monkeypatch.setattr("conformdag.checks.airflow.safety.run_ruff", lambda *_args: violations)

    findings = RuffAirEvaluator().evaluate(
        EvaluationContext(_ruff_policy(), [model], repository_root=tmp_path)
    )

    assert len(findings) == 1
    assert findings[0].location.start_line == 2


def test_ruff_evaluator_returns_no_findings_when_fallback_has_no_binary(
    tmp_path: Path, monkeypatch: Any
) -> None:
    model = _model("from airflow import DAG\ndag = DAG(dag_id='x')\n")
    monkeypatch.setattr("conformdag.checks.airflow.safety.run_ruff", lambda *_args: None)

    findings = RuffAirEvaluator().evaluate(
        EvaluationContext(_ruff_policy(), [model], repository_root=tmp_path)
    )

    assert findings == []
