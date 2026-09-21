"""Tests for direct discovery-module ownership."""

from pathlib import Path

from conformdag.analysis.discovery import DEFAULT_EXCLUDES, discover_python_files, matches_exclude
from conformdag.analysis.models import ParseIssueCode


def test_direct_discovery_preserves_recursive_excludes(tmp_path: Path) -> None:
    excluded = [
        ".venv/a.py",
        "src/a/.venv/x.py",
        "src/a/.git/hooks/example.py",
        "src/a/vendor/x.py",
    ]
    nearby = [".venv-copy/a.py", "src/a/.venv-copy/x.py", "src/a/vendorish/x.py"]
    selected = "src/a/kept.py"

    for relative in [*excluded, *nearby, selected]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("value = 1\n", encoding="utf-8")

    files, issues = discover_python_files(tmp_path, ["**/*.py"])

    assert [item.relative_path for item in files] == [*nearby, selected]
    assert issues == []
    assert matches_exclude("src/a/.venv/x.py", DEFAULT_EXCLUDES)
    assert not matches_exclude("src/a/.venv-copy/x.py", DEFAULT_EXCLUDES)


def test_direct_discovery_preserves_symlink_containment_issue_codes(tmp_path: Path) -> None:
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
        ParseIssueCode.EXTERNAL_SYMLINK_EXCLUDED,
        ParseIssueCode.BROKEN_SYMLINK_EXCLUDED,
    }
