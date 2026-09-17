"""End-to-end tests for the source-only scan path."""

import hashlib
from collections.abc import Sequence
from pathlib import Path
from shutil import copyfile, which
from typing import Any

import pytest
from ruamel.yaml import YAML

from conformdag.models import Confidence, FindingStatus, SemanticRequest, SemanticResponse
from conformdag.scan import scan_repository


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    yaml = YAML(typ="safe")
    with path.open("w", encoding="utf-8") as stream:
        yaml.dump(payload, stream)  # pyright: ignore[reportUnknownMemberType]


def _ruff_repository(root: Path, policy_specs: list[tuple[str, list[str]]]) -> Path:
    (root / "dags").mkdir()
    (root / "standards").mkdir()
    document = root / "standards/dag-authoring.md"
    document.write_text("# DAG Authoring Standards\n\n## Ownership and metadata\n", encoding="utf-8")
    content_hash = hashlib.sha256(document.read_bytes()).hexdigest()
    policies = [
        {
            "id": policy_id,
            "title": "Ruff AIR",
            "version": "1.0.0",
            "status": "ACTIVE",
            "severity": "medium",
            "airflow_profiles": ["3.3.0"],
            "ownership": {"owner": "platform"},
            "source": {
                "document": "standards/dag-authoring.md",
                "section": "Ownership and metadata",
                "version": "1",
                "content_hash": content_hash,
            },
            "invariant": "Ruff AIR violations are reported.",
            "safe_path": "Review the Ruff violation.",
            "enforcement": {
                "type": "deterministic",
                "deterministic_checks": ["ruff-air"],
                "blocking": True,
            },
            "configuration": {"kind": "ruff-air", "rules": rules},
        }
        for policy_id, rules in policy_specs
    ]
    pack_path = root / "pack.yaml"
    _write_yaml(
        pack_path,
        {
            "schema_version": "1",
            "id": "ruff-tests",
            "version": "1",
            "policies": policies,
        },
    )
    (root / "conformdag.yaml").write_text('config_version: "1"\n', encoding="utf-8")
    return pack_path


def _ruff_source(root: Path) -> None:
    (root / "dags/dag.py").write_text(
        "from airflow import DAG\ndag = DAG(dag_id='x')\n",
        encoding="utf-8",
    )


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


def test_scan_marks_unresolved_static_evaluation_incomplete(tmp_path: Path) -> None:
    (tmp_path / "policies").mkdir()
    (tmp_path / "standards").mkdir()
    (tmp_path / "dags").mkdir()
    copyfile("policies/pack.yaml", tmp_path / "policies/pack.yaml")
    copyfile("standards/dag-authoring.md", tmp_path / "standards/dag-authoring.md")
    (tmp_path / "dags" / "dynamic.py").write_text(
        "from airflow.decorators import task\n"
        "from airflow import DAG\n"
        "\n"
        "with DAG(dag_id='dynamic'):\n"
        "    @task(retries=RETRIES)\n"
        "    def work(): ...\n",
        encoding="utf-8",
    )

    report = scan_repository(tmp_path)

    retry = next(finding for finding in report.findings if finding.policy_id == "AIR-DET-004")
    assert retry.status is FindingStatus.ERROR
    assert report.complete is False
    evaluation_issues = [issue for issue in report.issues if issue.code == "EVALUATION_ERROR"]
    assert len(evaluation_issues) == 1
    assert evaluation_issues[0].fatal is True


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

    semantic_findings = [finding for finding in report.findings if finding.enforcement.value == "semantic"]
    assert len(semantic_findings) == 4
    assert report.run.semantic_provider == "openrouter.ai"
    assert report.run.semantic_model == "deepseek/deepseek-v4-flash"
    assert len(report.run.semantic_runs) == 4
    assert all(run.usage == {"total_tokens": 10} for run in report.run.semantic_runs)
    assert all(policy_id not in report.policies_skipped for policy_id in report.run.prompt_hashes)


def test_scan_accepts_external_policy_pack_from_working_directory(tmp_path: Path) -> None:
    foreign = tmp_path / "foreign-repo"
    (foreign / "dags").mkdir(parents=True)
    (foreign / "dags" / "example.py").write_text(
        "from airflow import DAG\ndag = DAG(owner='platform', tags=['domain:data', 'owner:platform'])\n",
        encoding="utf-8",
    )

    report = scan_repository(foreign, Path.cwd() / "policies/pack.yaml")

    assert report.complete is True
    assert len(report.files_scanned) == 1


def test_scan_accepts_bundled_community_pack_from_any_working_directory(tmp_path: Path) -> None:
    foreign = tmp_path / "foreign-repo"
    (foreign / "dags").mkdir(parents=True)
    (foreign / "dags" / "example.py").write_text(
        "from airflow import DAG\n"
        "from airflow.operators.empty import EmptyOperator\n"
        "with DAG(dag_id='example', default_args={'execution_timeout': 3600}) as dag:\n"
        "    EmptyOperator(task_id='start')\n",
        encoding="utf-8",
    )

    report = scan_repository(foreign, Path("community"))

    assert report.complete is True
    assert report.run.policy_pack_id == "conformdag-community"
    assert report.policies_evaluated == ["COM-DET-001", "COM-DET-002", "COM-DET-003"]


def test_scan_reports_ruff_unavailable_issue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pack_path = _ruff_repository(tmp_path, [("AIR-TST-002", ["AIR002"])])
    _ruff_source(tmp_path)

    monkeypatch.setattr("conformdag.scan.ruff_binary", lambda: None)

    report = scan_repository(tmp_path, pack_path)

    unavailable = [issue for issue in report.issues if issue.code == "RUFF_UNAVAILABLE"]
    assert len(unavailable) == 1
    assert unavailable[0].fatal is False
    assert report.complete is True


def test_scan_runs_ruff_once_with_union_rules_and_filters_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack_path = _ruff_repository(
        tmp_path,
        [("AIR-TST-002", ["AIR002"]), ("AIR-TST-003", ["AIR003"])],
    )
    _ruff_source(tmp_path)
    payload: list[dict[str, Any]] = [
        {
            "filename": str(tmp_path / "dags/dag.py"),
            "location": {"row": 2},
            "code": "AIR002",
            "message": "schedule is missing",
        },
        {
            "filename": str(tmp_path / "dags/dag.py"),
            "location": {"row": 2},
            "code": "AIR003",
            "message": "owner is missing",
        },
    ]
    calls: list[tuple[Path, list[str]]] = []

    def fake_run_ruff(root: Path, rules: list[str]) -> list[dict[str, Any]]:
        calls.append((root, rules))
        return payload

    monkeypatch.setattr("conformdag.scan.ruff_binary", lambda: "/usr/bin/ruff")
    monkeypatch.setattr("conformdag.scan.run_ruff", fake_run_ruff)

    report = scan_repository(tmp_path, pack_path)

    assert calls == [(tmp_path.resolve(), ["AIR002", "AIR003"])]
    findings = {
        finding.policy_id: (finding.location.file, finding.explanation)
        for finding in report.findings
        if finding.policy_id.startswith("AIR-TST-")
    }
    assert findings == {
        "AIR-TST-002": (Path("dags/dag.py"), "AIR002: schedule is missing"),
        "AIR-TST-003": (Path("dags/dag.py"), "AIR003: owner is missing"),
    }
    assert not any(issue.code == "RUFF_UNAVAILABLE" for issue in report.issues)


def test_scan_reports_ruff_invocation_failure_as_nonfatal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pack_path = _ruff_repository(tmp_path, [("AIR-TST-002", ["AIR002"])])
    _ruff_source(tmp_path)

    monkeypatch.setattr("conformdag.scan.ruff_binary", lambda: "/usr/bin/ruff")

    def fake_run_ruff(_root: Path, _rules: list[str]) -> None:
        return None

    monkeypatch.setattr("conformdag.scan.run_ruff", fake_run_ruff)

    report = scan_repository(tmp_path, pack_path)

    unavailable = [issue for issue in report.issues if issue.code == "RUFF_UNAVAILABLE"]
    assert len(unavailable) == 1
    assert unavailable[0].fatal is False
    assert report.complete is True


def test_scan_keeps_ruff_findings_suppressible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pack_path = _ruff_repository(tmp_path, [("AIR-TST-002", ["AIR002"])])
    _ruff_source(tmp_path)
    payload: list[dict[str, Any]] = [
        {
            "filename": str(tmp_path / "dags/dag.py"),
            "location": {"row": 2},
            "code": "AIR002",
            "message": "schedule is missing",
        }
    ]

    monkeypatch.setattr("conformdag.scan.ruff_binary", lambda: "/usr/bin/ruff")

    def fake_run_ruff(_root: Path, _rules: list[str]) -> list[dict[str, Any]]:
        return payload

    monkeypatch.setattr("conformdag.scan.run_ruff", fake_run_ruff)
    first = scan_repository(tmp_path, pack_path)
    finding = next(item for item in first.findings if item.policy_id == "AIR-TST-002")
    suppressions = tmp_path / ".conformdag/suppressions.yaml"
    suppressions.parent.mkdir()
    _write_yaml(
        suppressions,
        {
            "suppressions": [
                {
                    "fingerprint": finding.fingerprint,
                    "policy_id": finding.policy_id,
                    "reason": "known until the DAG is updated",
                    "owner": "platform",
                    "created_at": "2026-01-01T00:00:00Z",
                    "expires_at": "2099-01-01T00:00:00Z",
                }
            ]
        },
    )

    second = scan_repository(tmp_path, pack_path)

    suppressed = next(item for item in second.findings if item.policy_id == "AIR-TST-002")
    assert suppressed.suppressed is True
    assert not any(issue.code == "SUPPRESSION_UNMATCHED" for issue in second.issues)


@pytest.mark.skipif(which("ruff") is None, reason="ruff binary not installed")
def test_ruff_air_integration_catches_air002(tmp_path: Path) -> None:
    pack_path = _ruff_repository(tmp_path, [("AIR-TST-002", ["AIR002"])])
    _ruff_source(tmp_path)

    report = scan_repository(tmp_path, pack_path)

    ruff_findings = [finding for finding in report.findings if finding.policy_id == "AIR-TST-002"]
    assert any("AIR002" in (finding.explanation or "") for finding in ruff_findings)


@pytest.mark.skipif(which("ruff") is None, reason="ruff binary not installed")
def test_real_ruff_air_finding_is_suppressible(tmp_path: Path) -> None:
    pack_path = _ruff_repository(tmp_path, [("AIR-TST-002", ["AIR002"])])
    _ruff_source(tmp_path)

    first = scan_repository(tmp_path, pack_path)

    finding = next(item for item in first.findings if item.policy_id == "AIR-TST-002")
    assert finding.suppressed is False
    assert "AIR002" in (finding.explanation or "")
    suppressions = tmp_path / ".conformdag/suppressions.yaml"
    suppressions.parent.mkdir()
    _write_yaml(
        suppressions,
        {
            "suppressions": [
                {
                    "fingerprint": finding.fingerprint,
                    "policy_id": finding.policy_id,
                    "reason": "known until the DAG is updated",
                    "owner": "platform",
                    "created_at": "2026-01-01T00:00:00Z",
                    "expires_at": "2099-01-01T00:00:00Z",
                }
            ]
        },
    )

    second = scan_repository(tmp_path, pack_path)

    suppressed = next(item for item in second.findings if item.policy_id == "AIR-TST-002")
    assert suppressed.suppressed is True
    assert suppressed.suppression is not None
    assert not any(issue.code == "SUPPRESSION_UNMATCHED" for issue in second.issues)
