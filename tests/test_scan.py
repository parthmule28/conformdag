"""End-to-end tests for the source-only scan path."""

from collections.abc import Sequence
from pathlib import Path
from shutil import copyfile

from conformdag.models import Confidence, FindingStatus, SemanticRequest, SemanticResponse
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


class _SemanticProvider:
    def evaluate_many(
        self,
        requests: Sequence[SemanticRequest],
        max_concurrency: int = 4,
    ) -> list[SemanticResponse]:
        assert max_concurrency == 4
        return [
            SemanticResponse(
                status="NEEDS_REVIEW",
                evidence="bounded evidence",
                explanation="manual review is required",
                confidence=Confidence.MEDIUM,
                served_model="deepseek/deepseek-v4-flash",
                usage={"total_tokens": 10},
            )
            for _ in requests
        ]


def test_scan_merges_opt_in_semantic_findings_and_audit_metadata(tmp_path: Path) -> None:
    (tmp_path / "policies").mkdir()
    (tmp_path / "standards").mkdir()
    (tmp_path / "dags").mkdir()
    copyfile("policies/pack.yaml", tmp_path / "policies/pack.yaml")
    copyfile("standards/dag-authoring.md", tmp_path / "standards/dag-authoring.md")
    (tmp_path / "dags" / "example.py").write_text(
        "from airflow import DAG\ndag = DAG(owner='platform')\n",
        encoding="utf-8",
    )

    report = scan_repository(
        tmp_path,
        semantic_provider=_SemanticProvider(),
        semantic_provider_name="openrouter.ai",
        semantic_model="deepseek/deepseek-v4-flash",
    )

    semantic_findings = [
        finding for finding in report.findings if finding.enforcement.value == "semantic"
    ]
    assert len(semantic_findings) == 4
    assert report.run.semantic_provider == "openrouter.ai"
    assert report.run.semantic_model == "deepseek/deepseek-v4-flash"
    assert len(report.run.semantic_runs) == 4
    assert all(run.usage == {"total_tokens": 10} for run in report.run.semantic_runs)
    assert all(policy_id not in report.policies_skipped for policy_id in report.run.prompt_hashes)
