"""End-to-end tests for the source-only scan path."""

from pathlib import Path
from shutil import copyfile

from conformdag.models import FindingStatus
from conformdag.scan import scan_repository


def test_scan_supports_airflow_two_three_style_sources_without_execution(tmp_path: Path) -> None:
    (tmp_path / "policies").mkdir()
    (tmp_path / "standards").mkdir()
    (tmp_path / "dags").mkdir()
    copyfile("policies/pack.yaml", tmp_path / "policies/pack.yaml")
    copyfile("standards/dag-authoring.md", tmp_path / "standards/dag-authoring.md")
    (tmp_path / "conformdag.yaml").write_text(
        'config_version: "1"\nscan:\n  policy_pack: policies/pack.yaml\n',
        encoding="utf-8",
    )
    (tmp_path / "dags" / "airflow2.py").write_text(
        "from airflow import DAG\n"
        "default_args = {'owner': 'platform'}\n"
        "dag = DAG(default_args=default_args)\n"
        "raise RuntimeError('this module must not execute')\n",
        encoding="utf-8",
    )
    (tmp_path / "dags" / "airflow3.py").write_text(
        "from airflow.sdk import DAG\ndag = DAG(owner='unknown')\n",
        encoding="utf-8",
    )

    report = scan_repository(tmp_path)

    assert report.complete is True
    owner_findings = [item for item in report.findings if item.policy_id == "AIR-DET-001"]
    assert [item.status for item in owner_findings] == [FindingStatus.PASS, FindingStatus.FAIL]
    assert len(report.files_scanned) == 2
    assert report.issues == []


def test_scan_marks_parse_failures_incomplete(tmp_path: Path) -> None:
    (tmp_path / "policies").mkdir()
    (tmp_path / "standards").mkdir()
    (tmp_path / "dags").mkdir()
    copyfile("policies/pack.yaml", tmp_path / "policies/pack.yaml")
    copyfile("standards/dag-authoring.md", tmp_path / "standards/dag-authoring.md")
    (tmp_path / "dags" / "broken.py").write_text("def broken(:\n", encoding="utf-8")

    report = scan_repository(tmp_path)

    assert report.complete is False
    assert report.issues[0].code == "PARSE_ERROR"
