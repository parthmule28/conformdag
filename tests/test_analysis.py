"""Tests for source-only discovery and AST analysis."""

from os import stat_result
from pathlib import Path

import pytest

from conformdag.analysis import (
    DEFAULT_EXCLUDES,
    ParseCache,
    SourceFile,
    SourceModel,
    TaskRecord,
    analyze_source,
    discover_python_files,
    iter_module_scope_calls,
    matches_exclude,
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


def test_assigned_default_args_keep_unresolved_mapping_values_unresolved() -> None:
    source = (
        "from airflow import DAG\n"
        "DEFAULT_ARGS = {'owner': OWNER, 'retries': RETRIES}\n"
        "dag = DAG(default_args=DEFAULT_ARGS)\n"
    )

    model, issue = analyze_source(_source_file(source))

    assert issue is None
    assert model is not None
    assert model.dags[0].defaults == {}
    assert model.dags[0].unresolved_defaults == ("owner", "retries")


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


def test_excludes_match_at_any_nested_depth_without_matching_nearby_names() -> None:
    excluded = [
        ".venv/a.py",
        "src/.venv/a.py",
        "src/a/b/.venv/a.py",
        ".git/hooks/example.py",
        "src/.git/hooks/example.py",
        "vendor/a.py",
        "src/vendor/a.py",
        "src/a/vendor/a.py",
        "generated/a.py",
        "src/generated/a.py",
    ]
    nearby = [
        ".venv-copy/a.py",
        "src/vendorish/a.py",
        "src/a/not-vendor/a.py",
        "src/git/hooks/example.py",
        "src/a/generated-data/a.py",
    ]

    for relative in excluded:
        assert matches_exclude(relative, DEFAULT_EXCLUDES), relative
    for relative in nearby:
        assert not matches_exclude(relative, DEFAULT_EXCLUDES), relative


def test_discovery_excludes_nested_directories_at_arbitrary_depth(tmp_path: Path) -> None:
    excluded = [
        ".venv/a.py",
        "src/.venv/a.py",
        "src/a/b/.venv/a.py",
        ".git/hooks/example.py",
        "src/.git/hooks/example.py",
        "vendor/a.py",
        "src/vendor/a.py",
        "src/a/vendor/a.py",
    ]
    selected = "src/a/kept.py"
    for relative in [*excluded, selected]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("value = 1\n", encoding="utf-8")

    files, issues = discover_python_files(tmp_path, ["**/*.py"])

    assert [item.relative_path for item in files] == [selected]
    assert issues == []


def test_follow_internal_symlinks_never_reads_external_or_broken_targets(tmp_path: Path) -> None:
    dags = tmp_path / "dags"
    dags.mkdir()
    internal_target = dags / "internal_target.py"
    internal_target.write_text("internal = True\n", encoding="utf-8")
    internal_link = dags / "internal_link.py"
    internal_link.symlink_to(internal_target)

    external_target = tmp_path.parent / f"{tmp_path.name}-external.py"
    external_target.write_text("secret = 'outside'\n", encoding="utf-8")
    external_link = dags / "external_link.py"
    external_link.symlink_to(external_target)
    external_directory = tmp_path.parent / f"{tmp_path.name}-external-dir"
    external_directory.mkdir()
    (external_directory / "leaked.py").write_text("leaked = True\n", encoding="utf-8")
    external_directory_link = dags / "external_directory"
    external_directory_link.symlink_to(external_directory, target_is_directory=True)
    chained_link = dags / "chained_link.py"
    chained_target = dags / "chained_target.py"
    chained_target.symlink_to(external_target)
    chained_link.symlink_to(chained_target)
    broken_link = dags / "broken_link.py"
    broken_link.symlink_to(dags / "missing.py")

    files, issues = discover_python_files(tmp_path, ["dags/**/*.py"], follow_internal_symlinks=True)

    assert {item.relative_path for item in files} == {
        "dags/internal_link.py",
        "dags/internal_target.py",
    }
    assert all("outside" not in item.content for item in files)
    assert {issue.code for issue in issues} == {
        "EXTERNAL_SYMLINK_EXCLUDED",
        "BROKEN_SYMLINK_EXCLUDED",
    }


def test_discovery_reports_symlink_issue_code_when_not_following(tmp_path: Path) -> None:
    dags = tmp_path / "dags"
    dags.mkdir()
    target = dags / "target.py"
    target.write_text("value = 1\n", encoding="utf-8")
    link = dags / "link.py"
    link.symlink_to(target)

    files, issues = discover_python_files(tmp_path, ["dags/*.py"])

    assert [item.relative_path for item in files] == ["dags/target.py"]
    assert [(issue.code, issue.path) for issue in issues] == [("SYMLINK_EXCLUDED", "dags/link.py")]


def test_parse_cache_treats_empty_entries_as_misses(tmp_path: Path) -> None:
    cache = ParseCache(tmp_path / "cache")
    cache.directory.mkdir()
    (cache.directory / "abc.pkl").write_bytes(b"")

    assert cache.get("abc") is None


def test_parse_cache_replaces_atomically_and_preserves_last_good_entry_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = ParseCache(tmp_path / "cache")
    source = _source_file("value = 1\n")
    replacement = _source_file("value = 2\n")
    first, first_issue = analyze_source(source)
    second, second_issue = analyze_source(replacement)
    assert first_issue is None and first is not None
    assert second_issue is None and second is not None
    cache.put("abc", first)

    original_replace = Path.replace
    replacements: list[Path] = []

    def fail_replace(self: Path, target: Path) -> Path:
        replacements.append(self)
        raise OSError("simulated atomic replace failure")

    monkeypatch.setattr(Path, "replace", fail_replace)
    cache.put("abc", second)
    monkeypatch.setattr(Path, "replace", original_replace)

    cached = cache.get("abc")
    assert replacements
    assert cached is not None
    assert cached.source.content == source.content
    assert not list(cache.directory.glob(".*.tmp"))


def test_parse_cache_ignores_racing_prune_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = ParseCache(tmp_path / "cache")
    source = _source_file("value = 1\n")
    model, issue = analyze_source(source)
    assert issue is None and model is not None
    for index in range(499):
        cache.put(f"entry-{index}", model)

    original_stat = Path.stat

    def missing_stat(path: Path, *, follow_symlinks: bool = True) -> stat_result:
        if path.suffix == ".pkl":
            raise FileNotFoundError("entry disappeared during prune")
        return original_stat(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", missing_stat)

    cache.put("abc", model)

    assert cache.get("abc") is not None


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
