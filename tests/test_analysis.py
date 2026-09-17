"""Tests for source-only discovery and AST analysis."""

from pathlib import Path

from conformdag.analysis import (
    SourceFile,
    SourceModel,
    TaskRecord,
    analyze_source,
    discover_python_files,
    iter_module_scope_calls,
)


def _source_file(source: str) -> SourceFile:
    return SourceFile(
        path=Path("dags/x.py"),
        relative_path="dags/x.py",
        content=source,
        content_hash="e" * 64,
    )


def effective_retries(model: SourceModel, task: TaskRecord) -> object:
    """Mirror the evaluator's retries resolution to expose analysis-layer linkage."""
    if "retries" in task.values:
        return task.values["retries"]
    if task.dag_line is not None:
        for dag in model.dags:
            if dag.line == task.dag_line:
                return dag.defaults.get("retries")
    for dag in model.dags:
        if task.dag_name is None or task.dag_name == dag.variable_name:
            return dag.defaults.get("retries")
    return None


TWO_WITH_DAG_BLOCKS_REUSING_ALIAS = (
    "from airflow.decorators import task\n"
    "from airflow import DAG\n"
    "\n"
    "with DAG(dag_id='one', default_args={'retries': 1}) as dag:\n"
    "    @task\n"
    "    def first():\n"
    "        return 1\n"
    "\n"
    "with DAG(dag_id='two', default_args={'retries': 5}) as dag:\n"
    "    @task\n"
    "    def second():\n"
    "        return 2\n"
)


def test_reused_dag_alias_uses_nearest_concrete_dag_defaults() -> None:
    model, issue = analyze_source(_source_file(TWO_WITH_DAG_BLOCKS_REUSING_ALIAS))

    assert issue is None
    assert model is not None
    assert [task.dag_line for task in model.tasks] == [4, 9]
    assert [effective_retries(model, task) for task in model.tasks] == [1, 5]


def test_operator_unresolved_kwargs_are_tracked_and_bindings_resolved() -> None:
    source = (
        "from airflow import DAG\n"
        "from airflow.providers.standard.operators.empty import EmptyOperator\n"
        "KNOWN = 2\n"
        "dag = DAG(dag_id='x')\n"
        "task = EmptyOperator(task_id='t', dag=dag, retries=UNKNOWN, retry_delay=KNOWN)\n"
    )

    model, issue = analyze_source(_source_file(source))

    assert issue is None
    assert model is not None
    task = model.tasks[0]
    assert task.unresolved_kwargs == ("retries",)
    assert "retries" not in task.values
    assert task.values["retry_delay"] == 2
    assert task.dag_line == 4


def test_discovers_files_hashes_inputs_and_excludes_symlinks(tmp_path: Path) -> None:
    dags = tmp_path / "dags"
    dags.mkdir()
    source = dags / "example.py"
    source.write_text("from airflow import DAG\ndag = DAG(owner='platform')\n", encoding="utf-8")
    generated = dags / "generated"
    generated.mkdir()
    (generated / "example.py").write_text("x = 1\n", encoding="utf-8")

    files, issues = discover_python_files(tmp_path, ["dags/**/*.py"], ["**/generated/**"])

    assert [item.relative_path for item in files] == ["dags/example.py"]
    assert len(files[0].content_hash) == 64
    assert issues == []


def test_ast_analysis_does_not_execute_top_level_code(tmp_path: Path) -> None:
    source_path = tmp_path / "danger.py"
    source_path.write_text(
        "from airflow import DAG\n"
        "import requests\n"
        "requests.get('https://example.invalid')\n"
        "dag = DAG(owner='platform', tags=['data'])\n",
        encoding="utf-8",
    )
    files, _ = discover_python_files(tmp_path, ["*.py"])

    model, issue = analyze_source(files[0])

    assert issue is None
    assert model is not None
    assert model.dags[0].owner == "platform"
    assert model.dags[0].tags == ("data",)
    assert [call.qualified_name for call in iter_module_scope_calls(model)] == [
        "requests.get",
        "DAG",
    ]


def test_parse_errors_are_reported(tmp_path: Path) -> None:
    path = tmp_path / "broken.py"
    path.write_text("def broken(:\n", encoding="utf-8")
    files, _ = discover_python_files(tmp_path, ["*.py"])

    model, issue = analyze_source(files[0])

    assert model is None
    assert issue is not None
    assert issue.path == "broken.py"


def test_resolves_owner_from_supported_default_args_inheritance(tmp_path: Path) -> None:
    source_path = tmp_path / "inherited.py"
    source_path.write_text(
        "from airflow import DAG\ndefault_args = {'owner': 'platform'}\ndag = DAG(default_args=default_args)\n",
        encoding="utf-8",
    )
    files, _ = discover_python_files(tmp_path, ["*.py"])

    model, issue = analyze_source(files[0])

    assert issue is None
    assert model is not None
    assert model.dags[0].owner == "platform"
    assert model.dags[0].owner_source == "DAG.default_args.owner"
    assert model.dags[0].variable_name == "dag"


def test_taskflow_task_inside_with_dag_gets_dag_name() -> None:
    source = (
        "from airflow.decorators import task\n"
        "from airflow import DAG\n\n"
        "with DAG(dag_id='x') as dag:\n"
        "    @task\n"
        "    def extract():\n"
        "        return 1\n"
    )
    source_file = SourceFile(
        path=Path("dags/x.py"),
        relative_path="dags/x.py",
        content=source,
        content_hash="c" * 64,
    )

    model, issue = analyze_source(source_file)

    assert model is not None
    assert issue is None
    taskflow = [task for task in model.tasks if task.taskflow]
    assert len(taskflow) == 1
    assert taskflow[0].dag_name == "dag"


def test_taskflow_task_inside_unnamed_with_dag_has_no_dag_name() -> None:
    source = (
        "from airflow.decorators import task\n"
        "from airflow import DAG\n\n"
        "with DAG(dag_id='x'):\n"
        "    @task\n"
        "    def extract():\n"
        "        return 1\n"
    )
    source_file = SourceFile(
        path=Path("dags/x.py"),
        relative_path="dags/x.py",
        content=source,
        content_hash="d" * 64,
    )

    model, issue = analyze_source(source_file)

    assert model is not None
    assert issue is None
    taskflow = [task for task in model.tasks if task.taskflow]
    assert len(taskflow) == 1
    assert taskflow[0].dag_name is None
