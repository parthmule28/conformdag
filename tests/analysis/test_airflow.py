"""Tests for direct Airflow AST-analysis ownership."""

import ast
from pathlib import Path
from typing import cast

from conformdag.analysis.airflow import analyze_source, datetime_parts, iter_module_scope_calls
from conformdag.analysis.models import SourceFile, SourceModel


def _source_file(source: str) -> SourceFile:
    return SourceFile(
        path=Path("dags/x.py"),
        relative_path="dags/x.py",
        content=source,
        content_hash="f" * 64,
    )


def _analyze(source: str) -> SourceModel:
    model, issue = analyze_source(_source_file(source))
    assert issue is None
    assert model is not None
    return model


def test_direct_airflow_analysis_never_executes_source() -> None:
    model = _analyze(
        "raise RuntimeError('source must not execute')\n"
        "from airflow import DAG\n"
        "dag = DAG(dag_id='x', owner='platform')\n"
    )

    assert model.dags[0].owner == "platform"


def test_direct_airflow_analysis_preserves_taskflow_dag_context_and_unresolved_values() -> None:
    model = _analyze(
        "from airflow.decorators import task\n"
        "from airflow import DAG\n"
        "from airflow.providers.standard.operators.empty import EmptyOperator\n"
        "\n"
        "with DAG(dag_id='x') as dag:\n"
        "    @task\n"
        "    def extract():\n"
        "        return 1\n"
        "\n"
        "task = EmptyOperator(task_id='task', dag=dag, retries=UNKNOWN)\n"
    )

    taskflow = [task for task in model.tasks if task.taskflow]
    operator = [task for task in model.tasks if not task.taskflow]
    assert len(taskflow) == 1
    assert taskflow[0].dag_name == "dag"
    assert len(operator) == 1
    assert operator[0].unresolved_kwargs == ("retries",)


def test_direct_datetime_parts_preserves_timezone_detection() -> None:
    expression = cast(ast.Expr, ast.parse("datetime(2024, 1, 2, tzinfo=UTC)").body[0]).value

    assert datetime_parts(expression) == ((2024, 1, 2), True)


def test_direct_module_scope_calls_filters_nested_calls() -> None:
    model = _analyze(
        "import requests\n"
        "requests.get('module')\n"
        "def nested():\n"
        "    requests.post('nested')\n"
    )

    assert [call.qualified_name for call in iter_module_scope_calls(model)] == ["requests.get"]
