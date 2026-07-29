"""Tests for source-only discovery and AST analysis."""

from pathlib import Path

from conformdag.analysis import analyze_source, discover_python_files, iter_module_scope_calls


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
