"""CLI output and diagnostic routing tests."""

import hashlib
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from shutil import copyfile
from types import SimpleNamespace
from typing import Any, NoReturn, cast
from unittest.mock import patch

import pytest
from ruamel.yaml import YAML
from typer.core import TyperGroup, TyperOption
from typer.main import get_command
from typer.testing import CliRunner

from conformdag.application import (
    BaselineInput,
    EffectiveScanConfiguration,
    RuntimeExecutor,
    ScanExecutionResult,
    ScanOptions,
    ScanOverrides,
    resolve_effective_configuration,
)
from conformdag.cli import app
from conformdag.models import (
    AirflowProfile,
    EnforcementType,
    Finding,
    FindingEvidence,
    FindingLocation,
    FindingStatus,
    ProjectRuntimeConfig,
    RunMetadata,
    RuntimeObservation,
    ScanReport,
    Severity,
)
from conformdag.runtime import RuntimePhaseError
from conformdag.scan import SemanticProvider


def _missing_binary(_command: str) -> None:
    return None


def _docker_binary(_command: str) -> str:
    return "/usr/bin/docker"


def test_init_writes_quoted_scan_globs(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["init", "--path", str(tmp_path)])

    assert result.exit_code == 0
    config = (tmp_path / "conformdag.yaml").read_text(encoding="utf-8")
    assert '"dags/**/*.py"' in config
    assert "policy_pack: policies/pack.yaml" in config


def test_policy_hash_prints_sha256_of_document(tmp_path: Path) -> None:
    document = tmp_path / "standards.md"
    document.write_text("hello\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["policy", "hash", str(document)])

    assert result.exit_code == 0
    assert result.stdout.strip() == hashlib.sha256(b"hello\n").hexdigest()


def test_policy_new_rejects_unknown_kind() -> None:
    result = CliRunner().invoke(app, ["policy", "new", "AIR-TST-999", "--kind", "nope"])

    assert result.exit_code != 0
    assert "unknown check kind" in result.stderr


@pytest.mark.parametrize("kind", ["idempotence", "orchestration-boundary", "approved-abstractions"])
def test_policy_new_rejects_non_executable_catalogue_kind(kind: str) -> None:
    result = CliRunner().invoke(app, ["policy", "new", "AIR-TST-999", "--kind", kind])

    assert result.exit_code != 0
    assert "unknown check kind" in result.stderr


def test_policy_configuration_delegates_to_catalogue(monkeypatch: pytest.MonkeyPatch) -> None:
    import conformdag.cli as cli_module

    expected = {"kind": "required-owner", "allowed_values": ["catalogue"]}

    def fake_check_spec(kind: str) -> SimpleNamespace:
        assert kind == "effective-owner"
        return SimpleNamespace(evaluator=object(), scaffold_factory=lambda: expected.copy())

    monkeypatch.setattr(cli_module, "check_spec", fake_check_spec)
    policy_configuration = cast(Callable[[str], dict[str, object]], cli_module.__dict__["_policy_configuration"])

    assert policy_configuration("effective-owner") == expected


def test_policy_new_scaffolds_valid_policy_for_every_registered_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conformdag.evaluator import CHECK_EVALUATORS
    from conformdag.models import Policy, PolicyPack
    from conformdag.policy import validate_policy_provenance

    document = tmp_path / "standards" / "dag-authoring.md"
    document.parent.mkdir()
    document.write_text(
        "# DAG Authoring Standards\n\n## Execution safety\n\nUse safe defaults.\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    for index, kind in enumerate(CHECK_EVALUATORS):
        result = CliRunner().invoke(app, ["policy", "new", f"AIR-TST-{index:03d}", "--kind", kind])

        assert result.exit_code == 0, result.stderr
        block = YAML(typ="safe").load(result.stdout)  # pyright: ignore[reportUnknownMemberType]
        policy = Policy.model_validate(block)
        pack = PolicyPack(schema_version="1", id="test", version="1", policies=[policy])
        assert (
            validate_policy_provenance(
                pack,
                pack_path=tmp_path / "policies" / "pack.yaml",
                repository_root=tmp_path,
            )
            == []
        )
        if kind == "ruff-air":
            assert block["configuration"]["rules"] == ["AIR001", "AIR002", "AIR301", "AIR302", "AIR311", "AIR312"]


def test_init_writes_workspace_scaffold(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["init", "--path", str(tmp_path)])

    assert result.exit_code == 0
    workspace = (tmp_path / "conformdag-workspace.yaml").read_text(encoding="utf-8")
    assert "schema_version" in workspace
    assert "policy_packs:" in workspace


def test_doctor_reports_healthy_tmp_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert CliRunner().invoke(app, ["init", "--path", str(tmp_path)]).exit_code == 0
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CONFORMDAG_PLATFORM_DSN", raising=False)
    monkeypatch.setattr("conformdag.cli.shutil.which", _missing_binary)

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "config" in result.stdout
    assert "pack" in result.stdout
    assert "WARN docker" in result.stdout


def test_doctor_reports_platform_dsn_reachability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert CliRunner().invoke(app, ["init", "--path", str(tmp_path)]).exit_code == 0
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFORMDAG_PLATFORM_DSN", f"sqlite:///{tmp_path / 'platform.db'}")
    monkeypatch.setattr("conformdag.cli.shutil.which", _docker_binary)

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "platform-dsn" in result.stdout
    assert "reachable" in result.stdout


def test_doctor_uses_configured_policy_pack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "policies").mkdir()
    (tmp_path / "configured").mkdir()
    _write_yaml(
        tmp_path / "policies" / "pack.yaml",
        {"schema_version": "1", "id": "implicit", "version": "1", "policies": []},
    )
    _write_yaml(
        tmp_path / "configured" / "pack.yaml",
        {"schema_version": "1", "id": "configured", "version": "1", "policies": []},
    )
    (tmp_path / "conformdag.yaml").write_text(
        'config_version: "1"\nscan:\n  policy_pack: configured/pack.yaml\n', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CONFORMDAG_PLATFORM_DSN", raising=False)
    monkeypatch.setattr("conformdag.cli.shutil.which", _docker_binary)

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "PASS pack: configured 1" in result.stdout


def test_doctor_accepts_the_real_org_pack(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    monkeypatch.delenv("CONFORMDAG_PLATFORM_DSN", raising=False)
    monkeypatch.setattr("conformdag.cli.shutil.which", _docker_binary)

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0, result.stderr
    assert "PASS pack: conformdag-default" in result.stdout


def test_doctor_reports_unknown_hybrid_deterministic_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "policies").mkdir()
    standards = tmp_path / "standards" / "dag-authoring.md"
    standards.parent.mkdir()
    standards.write_text("# DAG Authoring Standards\n\n## Ownership and metadata\n", encoding="utf-8")
    content_hash = hashlib.sha256(standards.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    _write_yaml(
        tmp_path / "policies" / "pack.yaml",
        {
            "schema_version": "1",
            "id": "hybrid-pack",
            "version": "1",
            "policies": [
                {
                    "id": "AIR-TST-900",
                    "title": "Hybrid policy",
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
                    "invariant": "Hybrid checks use registered deterministic evaluators.",
                    "safe_path": "Use a registered deterministic check.",
                    "enforcement": {
                        "type": "hybrid",
                        "deterministic_checks": ["unknown-hybrid"],
                        "model_check": True,
                    },
                    "configuration": {"kind": "required-owner", "allowed_values": ["platform"]},
                }
            ],
        },
    )
    (tmp_path / "conformdag.yaml").write_text('config_version: "1"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CONFORMDAG_PLATFORM_DSN", raising=False)
    monkeypatch.setattr("conformdag.cli.shutil.which", _docker_binary)

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "unknown deterministic check 'unknown-hybrid'" in result.stdout


def test_baseline_set_reports_platform_initialization_sqlalchemy_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.exc import SQLAlchemyError

    monkeypatch.setenv("CONFORMDAG_PLATFORM_DSN", "sqlite:///platform.db")
    monkeypatch.setenv("CONFORMDAG_PLATFORM_TOKEN", "secret-token")

    def fail_initialize_session_factory(_dsn: str) -> NoReturn:
        raise SQLAlchemyError("migration failed")

    monkeypatch.setattr("conformdag.platform.db.initialize_session_factory", fail_initialize_session_factory)

    result = CliRunner().invoke(app, ["baseline", "set", "scan1"])

    assert result.exit_code == 2
    assert "migration failed" in result.stderr


def test_doctor_fails_when_configured_platform_dsn_is_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert CliRunner().invoke(app, ["init", "--path", str(tmp_path)]).exit_code == 0
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFORMDAG_PLATFORM_DSN", "postgresql://invalid-host.invalid/conformdag")
    monkeypatch.setattr("conformdag.cli.shutil.which", _docker_binary)

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "FAIL platform-dsn" in result.stdout


def test_baseline_set_marks_scan_in_platform_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from conformdag.platform.db import RepositoryRow, ScanRow, initialize_session_factory

    dsn = f"sqlite:///{tmp_path / 'platform.db'}"
    monkeypatch.setenv("CONFORMDAG_PLATFORM_DSN", dsn)
    monkeypatch.setenv("CONFORMDAG_PLATFORM_TOKEN", "secret-token")
    factory = initialize_session_factory(dsn)
    with factory() as session:
        session.add(RepositoryRow(id="repo1", name="core-dags", path=str(tmp_path)))
        session.add(ScanRow(id="scan1", repository_id="repo1", status="succeeded", complete=True))
        session.commit()

    result = CliRunner().invoke(app, ["baseline", "set", "scan1"])

    assert result.exit_code == 0
    assert "baseline set" in result.stdout
    with factory() as session:
        repository = session.get(RepositoryRow, "repo1")
        assert repository is not None
        assert repository.baseline_scan_id == "scan1"


def test_baseline_eligibility_rejects_ineligible_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from conformdag.platform.db import RepositoryRow, ScanRow, initialize_session_factory

    dsn = f"sqlite:///{tmp_path / 'platform.db'}"
    monkeypatch.setenv("CONFORMDAG_PLATFORM_DSN", dsn)
    monkeypatch.setenv("CONFORMDAG_PLATFORM_TOKEN", "secret-token")
    factory = initialize_session_factory(dsn)
    with factory() as session:
        session.add(RepositoryRow(id="repo1", name="core-dags", path=str(tmp_path)))
        for status in ("queued", "failed", "cancelled"):
            session.add(ScanRow(id=f"scan-{status}", repository_id="repo1", status=status))
        session.add(ScanRow(id="scan-incomplete", repository_id="repo1", status="succeeded", complete=False))
        session.commit()

    for scan_id in ("scan-queued", "scan-failed", "scan-cancelled", "scan-incomplete"):
        result = CliRunner().invoke(app, ["baseline", "set", scan_id])

        assert result.exit_code == 2
        assert "eligible" in result.stderr
        assert result.stderr.count("error:") == 1, "intentional exits must not be re-caught and re-failed"

    with factory() as session:
        repository = session.get(RepositoryRow, "repo1")
        assert repository is not None
        assert repository.baseline_scan_id is None


def test_baseline_set_missing_scan_reports_single_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from conformdag.platform.db import RepositoryRow, initialize_session_factory

    dsn = f"sqlite:///{tmp_path / 'platform.db'}"
    monkeypatch.setenv("CONFORMDAG_PLATFORM_DSN", dsn)
    monkeypatch.setenv("CONFORMDAG_PLATFORM_TOKEN", "secret-token")
    factory = initialize_session_factory(dsn)
    with factory() as session:
        session.add(RepositoryRow(id="repo1", name="core-dags", path=str(tmp_path)))
        session.commit()

    result = CliRunner().invoke(app, ["baseline", "set", "missing-scan"])

    assert result.exit_code == 2
    assert result.stderr.count("error:") == 1
    assert "scan not found: missing-scan" in result.stderr


def test_validate_policies_accepts_bundled_community_alias() -> None:
    result = CliRunner().invoke(app, ["validate-policies", "--path", "community"])

    assert result.exit_code == 0
    assert "valid policy pack: conformdag-community" in result.stdout


def test_validate_policies_rejects_unknown_gate_policy_references(tmp_path: Path) -> None:
    (tmp_path / "policies").mkdir()
    (tmp_path / "standards").mkdir()
    (tmp_path / "standards/dag-authoring.md").write_text("# DAG Authoring Standards\n", encoding="utf-8")
    (tmp_path / "policies/pack.yaml").write_text(
        "schema_version: '1'\n"
        "id: x\n"
        "version: '1'\n"
        "policies: []\n"
        "quality_gates:\n"
        "  - id: default\n"
        "    rules:\n"
        "      - type: always-block\n"
        "        policy_ids: [AIR-DET-999]\n",
        encoding="utf-8",
    )
    (tmp_path / "conformdag.yaml").write_text('config_version: "1"\n', encoding="utf-8")

    result = CliRunner().invoke(app, ["validate-policies", "--path", str(tmp_path / "policies" / "pack.yaml")])

    assert result.exit_code != 0
    assert "AIR-DET-999" in result.stderr


def test_scan_fails_closed_on_unknown_check(tmp_path: Path) -> None:
    root = _write_gate_repo(tmp_path, with_gate=False, owner=None)
    pack: dict[str, Any] = YAML(typ="safe").load((root / "pack.yaml").read_text(encoding="utf-8"))  # pyright: ignore[reportUnknownMemberType]
    pack["policies"][0]["enforcement"]["deterministic_checks"] = ["missing-check"]
    _write_yaml(root / "pack.yaml", pack)

    result = CliRunner().invoke(
        app, ["scan", "--path", str(root), "--policy-pack", str(root / "pack.yaml"), "--format", "json"]
    )

    assert result.exit_code == 2
    assert "unknown deterministic check" in result.stderr


def test_validate_policies_fails_closed_on_unknown_check(tmp_path: Path) -> None:
    (tmp_path / "policies").mkdir()
    (tmp_path / "standards").mkdir()
    content = "# DAG Authoring Standards\n\n## Ownership and metadata\n"
    (tmp_path / "standards/dag-authoring.md").write_text(content, encoding="utf-8")
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    (tmp_path / "policies/pack.yaml").write_text(
        "schema_version: '1'\n"
        "id: x\n"
        "version: '1'\n"
        "policies:\n"
        "  - id: AIR-TST-901\n"
        "    title: Owner policy\n"
        "    version: '1.0.0'\n"
        "    status: ACTIVE\n"
        "    severity: high\n"
        "    airflow_profiles: ['3.3.0']\n"
        "    ownership: {owner: platform}\n"
        "    source:\n"
        "      document: standards/dag-authoring.md\n"
        "      section: Ownership and metadata\n"
        f"      content_hash: '{content_hash}'\n"
        "    invariant: Every DAG declares an owner.\n"
        "    safe_path: An owner is present.\n"
        "    enforcement: {type: deterministic, deterministic_checks: [missing-check]}\n"
        "    configuration: {kind: required-owner, allowed_values: [platform]}\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["validate-policies", "--path", str(tmp_path / "policies" / "pack.yaml")])

    assert result.exit_code == 2
    assert "unknown deterministic check" in result.stderr


def test_terminal_scan_output_is_human_readable() -> None:
    result = CliRunner().invoke(app, ["scan", "--path", ".", "--format", "terminal"])

    assert result.exit_code == 0
    assert "ConformDAG scan complete" in result.stdout
    assert "Result fingerprint:" in result.stdout
    assert "scan complete:" in result.stderr


def test_json_scan_output_is_machine_readable_and_keeps_diagnostics_off_stdout() -> None:
    result = CliRunner().invoke(app, ["scan", "--path", ".", "--format", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["report_version"] == "2"
    assert "scan complete:" not in result.stdout
    assert "scan complete:" in result.stderr


def test_sarif_and_html_outputs_are_parseable_files(tmp_path: Path) -> None:
    sarif_path = tmp_path / "report.sarif"
    sarif = CliRunner().invoke(app, ["scan", "--path", ".", "--format", "sarif", "--output", str(sarif_path)])
    assert sarif.exit_code == 0
    sarif_payload = json.loads(sarif_path.read_text(encoding="utf-8"))
    assert sarif_payload["version"] == "2.1.0"
    assert sarif_payload["runs"][0]["automationDetails"]["id"]

    html_path = tmp_path / "report.html"
    html = CliRunner().invoke(
        app,
        [
            "scan",
            "--path",
            ".",
            "--format",
            "html",
            "--output",
            str(html_path),
            "--no-evidence",
        ],
    )
    assert html.exit_code == 0
    rendered = html_path.read_text(encoding="utf-8")
    assert '<html lang="en">' in rendered
    assert '<th scope="col">Policy</th>' in rendered
    assert "DAG owner=" not in rendered


def test_html_scan_requires_an_explicit_destination() -> None:
    result = CliRunner().invoke(app, ["scan", "--path", ".", "--format", "html"])

    assert result.exit_code == 2
    assert "HTML output requires --output" in result.output


def test_preview_model_context_is_local_and_provider_free() -> None:
    result = CliRunner().invoke(app, ["scan", "--path", ".", "--preview-model-context"])

    assert result.exit_code == 0
    assert '"context_hash"' in result.stdout
    assert '"redacted_context"' in result.stdout


def test_runtime_profile_is_explicitly_selectable() -> None:
    digest = "ghcr.io/example/conformdag@sha256:" + "a" * 64
    with patch(
        "conformdag.cli.execute_runtime",
        return_value=(
            [RuntimeObservation(status=FindingStatus.PASS, policy_id="AIR-DET-001")],
            digest,
        ),
    ):
        result = CliRunner().invoke(app, ["scan", "--path", ".", "--runtime", "3.3.0"])

    assert result.exit_code == 0
    assert "scan complete:" in result.stderr
    assert json.loads(result.stdout)["run"]["runtime_image_digest"] == digest


def test_runtime_profile_and_custom_image_are_mutually_exclusive() -> None:
    result = CliRunner().invoke(
        app,
        [
            "scan",
            "--path",
            ".",
            "--runtime",
            "3.3.0",
            "--runtime-image",
            "airflow@sha256:" + "a" * 64,
        ],
    )

    assert result.exit_code == 2
    assert "cannot be used together" in result.output


def test_runtime_execution_failure_is_a_structured_incomplete_report() -> None:
    with patch(
        "conformdag.cli.execute_runtime",
        side_effect=RuntimePhaseError("Docker daemon is unavailable"),
    ):
        result = CliRunner().invoke(app, ["scan", "--path", ".", "--runtime", "3.3.0"])

    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["complete"] is False
    assert payload["issues"][-1]["code"] == "RUNTIME_EXECUTION_ERROR"


def test_agent_run_preserves_blocked_verifier_as_cli_failure(tmp_path: Path) -> None:
    from conformdag.agent import AgentOutcome

    blocked = AgentOutcome(changed=True, diff="verified diff", blocked=True)
    with patch("conformdag.agent.run_agent_pipeline", return_value=blocked):
        result = CliRunner().invoke(app, ["agent", "run", "--path", str(tmp_path), "--no-verifier"])

    assert result.exit_code == 1
    assert "pull request blocked by verifier verdict" in result.stderr


def test_scan_exits_three_when_static_evaluation_is_unresolved(tmp_path: Path) -> None:
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

    result = CliRunner().invoke(app, ["scan", "--path", str(tmp_path)])

    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["complete"] is False
    assert any(issue["code"] == "EVALUATION_ERROR" for issue in payload["issues"])
    assert "scan incomplete" in result.stderr


def test_custom_runtime_image_requires_digest() -> None:
    result = CliRunner().invoke(
        app,
        ["scan", "--path", ".", "--runtime-image", "airflow:latest"],
    )

    assert result.exit_code == 2
    assert "immutable sha256 digest" in result.output


def test_scan_help_exposes_single_purpose_boolean_flags() -> None:
    result = CliRunner().invoke(app, ["scan", "--help"], env={"COLUMNS": "200"})

    assert result.exit_code == 0
    root_command = get_command(app)
    assert isinstance(root_command, TyperGroup)
    scan_command = root_command.commands["scan"]
    option_names = {
        option_name
        for parameter in scan_command.params
        if isinstance(parameter, TyperOption)
        for option_name in (*parameter.opts, *parameter.secondary_opts)
    }

    assert "--no-evidence" in option_names
    assert "--no-no-evidence" not in option_names
    assert "--preview-model-context" in option_names
    assert "--no-preview-model-context" not in option_names
    assert "--semantic" in option_names
    assert "--semantic-structured-output" in option_names


def test_semantic_scan_requires_environment_only_api_key() -> None:
    environment = dict(os.environ)
    environment.pop("CONFORMDAG_MODEL_API_KEY", None)
    with patch.dict(os.environ, environment, clear=True):
        result = CliRunner().invoke(
            app,
            [
                "scan",
                "--path",
                ".",
                "--semantic",
                "--semantic-base-url",
                "https://openrouter.ai/api/v1",
                "--semantic-model",
                "deepseek/deepseek-v4-flash",
            ],
        )

    assert result.exit_code == 2
    assert "CONFORMDAG_MODEL_API_KEY" in result.output


def test_semantic_scan_rejects_non_loopback_plain_http() -> None:
    with patch.dict(os.environ, {"CONFORMDAG_MODEL_API_KEY": "test-key"}):
        result = CliRunner().invoke(
            app,
            [
                "scan",
                "--path",
                ".",
                "--semantic",
                "--semantic-base-url",
                "http://model.example/v1",
                "--semantic-model",
                "test-model",
            ],
        )

    assert result.exit_code == 2
    assert "must use HTTPS" in result.output


def test_policy_show_is_human_readable() -> None:
    result = CliRunner().invoke(
        app,
        ["policy", "show", "AIR-DET-001", "--path", "policies/pack.yaml"],
    )

    assert result.exit_code == 0
    assert "ID: AIR-DET-001" in result.stdout
    assert "Enforcement: deterministic" in result.stdout


def test_policy_review_contains_contract_and_provenance() -> None:
    result = CliRunner().invoke(
        app,
        ["policy", "review", "AIR-DET-001", "--path", "policies/pack.yaml"],
    )

    assert result.exit_code == 0
    assert "Policy review: AIR-DET-001" in result.stdout
    assert "Invariant:" in result.stdout
    assert "content hash:" in result.stdout
    assert "Enforcement configuration:" in result.stdout


def test_policy_explain_is_machine_readable_json() -> None:
    result = CliRunner().invoke(
        app,
        ["policy", "explain", "AIR-DET-001", "--path", "policies/pack.yaml"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["id"] == "AIR-DET-001"


def test_policy_reference_describes_outcomes_and_supports_json() -> None:
    result = CliRunner().invoke(app, ["policy", "reference", "outcomes"])

    assert result.exit_code == 0
    assert "Outcomes" in result.stdout
    assert "NEEDS_REVIEW" in result.stdout

    machine = CliRunner().invoke(
        app,
        ["policy", "reference", "runtime", "--format", "json"],
    )

    assert machine.exit_code == 0
    assert json.loads(machine.stdout)["runtime"][0]["key"] == "manifest"


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        YAML(typ="safe").dump(payload, handle)  # pyright: ignore[reportUnknownMemberType]


def _write_gate_repo(tmp_path: Path, *, with_gate: bool, owner: str | None, count: int = 1) -> Path:
    """Create a repo + pack with one owner policy and (optionally) a max-findings gate."""
    (tmp_path / "dags").mkdir()
    owner_kwarg = f", owner='{owner}'" if owner else ""
    (tmp_path / "dags/dag.py").write_text(
        f"from airflow import DAG\ndag = DAG(dag_id='x'{owner_kwarg})\n", encoding="utf-8"
    )
    (tmp_path / "standards").mkdir()
    document = tmp_path / "standards/dag-authoring.md"
    document.write_text("# DAG Authoring Standards\n\n## Ownership and metadata\n", encoding="utf-8")
    content_hash = hashlib.sha256(document.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    pack: dict[str, Any] = {
        "schema_version": "1",
        "id": "x",
        "version": "1",
        "policies": [
            {
                "id": "AIR-TST-001",
                "title": "owner",
                "version": "1.0.0",
                "status": "ACTIVE",
                "severity": "high",
                "airflow_profiles": ["3.3.0"],
                "ownership": {"owner": "platform"},
                "source": {
                    "document": "standards/dag-authoring.md",
                    "section": "Ownership and metadata",
                    "version": "1",
                    "content_hash": content_hash,
                },
                "invariant": "Every DAG declares an owner.",
                "safe_path": "An owner is present.",
                "enforcement": {"type": "deterministic", "deterministic_checks": ["effective-owner"], "blocking": True},
                "configuration": {"kind": "required-owner", "allowed_values": ["platform"]},
            }
        ],
    }
    if with_gate:
        pack["quality_gates"] = [{"id": "default", "rules": [{"type": "max-findings", "count": count}]}]
    _write_yaml(tmp_path / "pack.yaml", pack)
    (tmp_path / "conformdag.yaml").write_text('config_version: "1"\n', encoding="utf-8")
    return tmp_path


def test_scan_exits_zero_when_gate_passes_despite_findings(tmp_path: Path) -> None:
    root = _write_gate_repo(tmp_path, with_gate=True, owner=None, count=2)

    result = CliRunner().invoke(
        app, ["scan", "--path", str(root), "--policy-pack", str(root / "pack.yaml"), "--format", "json"]
    )

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["gate_result"]["gate_id"] == "default"
    assert report["gate_result"]["passed"] is True


def test_scan_exits_one_when_gate_fails(tmp_path: Path) -> None:
    root = _write_gate_repo(tmp_path, with_gate=True, owner=None)
    (tmp_path / "dags" / "dag.py").write_text("from airflow import DAG\ndag = DAG(dag_id='x')\n", encoding="utf-8")
    second = tmp_path / "dags" / "dag2.py"
    second.write_text("from airflow import DAG\ndag2 = DAG(dag_id='y')\n", encoding="utf-8")

    result = CliRunner().invoke(
        app, ["scan", "--path", str(root), "--policy-pack", str(root / "pack.yaml"), "--format", "json"]
    )

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["gate_result"]["passed"] is False


def test_scan_without_gates_keeps_legacy_exit_code(tmp_path: Path) -> None:
    root = _write_gate_repo(tmp_path, with_gate=False, owner=None)

    result = CliRunner().invoke(
        app, ["scan", "--path", str(root), "--policy-pack", str(root / "pack.yaml"), "--format", "json"]
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout)["gate_result"] is None


def test_scan_baseline_satisfies_no_new_findings(tmp_path: Path) -> None:
    root = _write_gate_repo(tmp_path, with_gate=False, owner=None)
    baseline = CliRunner().invoke(
        app,
        [
            "scan",
            "--path",
            str(root),
            "--policy-pack",
            str(root / "pack.yaml"),
            "--format",
            "json",
            "--output",
            str(root / "baseline.json"),
        ],
    )
    assert baseline.exit_code == 1
    pack_text = (root / "pack.yaml").read_text(encoding="utf-8")
    pack: dict[str, Any] = YAML(typ="safe").load(pack_text)  # pyright: ignore[reportUnknownMemberType]
    pack["quality_gates"] = [{"id": "default", "rules": [{"type": "no-new-findings"}]}]
    _write_yaml(root / "pack.yaml", pack)

    result = CliRunner().invoke(
        app,
        [
            "scan",
            "--path",
            str(root),
            "--policy-pack",
            str(root / "pack.yaml"),
            "--baseline",
            str(root / "baseline.json"),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["gate_result"]["passed"] is True


def test_scan_rejects_incomplete_report_as_baseline(tmp_path: Path) -> None:
    root = _write_gate_repo(tmp_path, with_gate=True, owner=None, count=2)
    baseline = CliRunner().invoke(
        app,
        [
            "scan",
            "--path",
            str(root),
            "--policy-pack",
            str(root / "pack.yaml"),
            "--format",
            "json",
            "--output",
            str(root / "baseline.json"),
        ],
    )
    assert baseline.exit_code == 0
    payload = json.loads((root / "baseline.json").read_text(encoding="utf-8"))
    payload["complete"] = False
    (root / "baseline.json").write_text(json.dumps(payload), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "scan",
            "--path",
            str(root),
            "--policy-pack",
            str(root / "pack.yaml"),
            "--baseline",
            str(root / "baseline.json"),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 2
    assert "incomplete" in result.stderr


def test_scan_uses_configured_pack_for_gate_evaluation(tmp_path: Path) -> None:
    root = _write_gate_repo(tmp_path, with_gate=True, owner=None, count=2)
    configured_dir = root / "configured"
    configured_dir.mkdir()
    (configured_dir / "pack.yaml").write_text((root / "pack.yaml").read_text(encoding="utf-8"), encoding="utf-8")

    implicit_dir = root / "policies"
    implicit_dir.mkdir()
    implicit_pack: dict[str, Any] = YAML(typ="safe").load(  # pyright: ignore[reportUnknownMemberType]
        (root / "pack.yaml").read_text(encoding="utf-8")
    )
    implicit_pack["quality_gates"] = [{"id": "implicit", "rules": [{"type": "max-findings", "count": 1}]}]
    _write_yaml(implicit_dir / "pack.yaml", implicit_pack)
    (root / "conformdag.yaml").write_text(
        'config_version: "1"\nscan:\n  policy_pack: configured/pack.yaml\n', encoding="utf-8"
    )

    result = CliRunner().invoke(app, ["scan", "--path", str(root), "--format", "json"])

    assert result.exit_code == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["gate_result"]["gate_id"] == "default"
    assert report["gate_result"]["passed"] is True


def test_scan_incomplete_report_does_not_embed_gate_result(tmp_path: Path) -> None:
    root = _write_gate_repo(tmp_path, with_gate=True, owner=None, count=2)
    (root / "dags" / "broken.py").write_text("def broken(:\n", encoding="utf-8")

    result = CliRunner().invoke(
        app, ["scan", "--path", str(root), "--policy-pack", str(root / "pack.yaml"), "--format", "json"]
    )

    assert result.exit_code == 3
    report = json.loads(result.stdout)
    assert report["complete"] is False
    assert report["gate_result"] is None


def _application_report(*, include_finding: bool = False) -> ScanReport:
    findings = (
        [
            Finding(
                policy_id="AIR-TST-001",
                policy_version="1.0.0",
                status=FindingStatus.PASS,
                severity=Severity.HIGH,
                enforcement=EnforcementType.DETERMINISTIC,
                location=FindingLocation(file=Path("dags/dag.py"), start_line=1),
                evidence=FindingEvidence(text="DAG owner='sensitive-value'", start_line=1),
                fingerprint="f" * 64,
            )
        ]
        if include_finding
        else []
    )
    return ScanReport(
        complete=True,
        result_fingerprint="application-service-fingerprint",
        findings=findings,
        issues=[],
        run=RunMetadata(
            tool_version="test",
            policy_pack_id="test-pack",
            policy_pack_version="1",
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )


@pytest.mark.parametrize("runtime_enabled", [False, True])
def test_scan_delegates_to_application_service_with_adapter_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runtime_enabled: bool,
) -> None:
    root = _write_gate_repo(tmp_path, with_gate=False, owner="platform")
    if runtime_enabled:
        _write_yaml(
            root / "conformdag.yaml",
            {"config_version": "1", "runtime": {"enabled": True, "airflow_version": "3.3.0"}},
        )
    baseline_path = root / "baseline.json"
    expected_baseline = _application_report()
    baseline_path.write_text(expected_baseline.model_dump_json(), encoding="utf-8")
    calls: list[
        tuple[
            ScanOptions,
            EffectiveScanConfiguration,
            SemanticProvider | None,
            str | None,
            RuntimeExecutor | None,
            BaselineInput | None,
        ]
    ] = []
    service_report = _application_report()

    def execute_service(
        options: ScanOptions,
        configuration: EffectiveScanConfiguration,
        *,
        semantic_provider: SemanticProvider | None = None,
        semantic_provider_name: str | None = None,
        runtime_executor: RuntimeExecutor | None = None,
        baseline: BaselineInput | None = None,
    ) -> ScanExecutionResult:
        calls.append(
            (
                options,
                configuration,
                semantic_provider,
                semantic_provider_name,
                runtime_executor,
                baseline,
            )
        )
        return ScanExecutionResult(report=service_report, gate_result=None)

    monkeypatch.setattr("conformdag.cli.execute_scan", execute_service, raising=False)

    def fake_runtime(
        root: Path,
        config: ProjectRuntimeConfig,
        policy_ids: list[str],
        include: list[str],
        exclude: list[str],
    ) -> tuple[list[RuntimeObservation], str]:
        return [RuntimeObservation(status=FindingStatus.PASS, policy_id="AIR-TST-001")], "sha256:test"

    if runtime_enabled:
        monkeypatch.setattr("conformdag.cli.execute_runtime", fake_runtime)

    result = CliRunner().invoke(
        app,
        [
            "scan",
            "--path",
            str(root),
            "--policy-pack",
            str(root / "pack.yaml"),
            "--baseline",
            str(baseline_path),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.stderr
    assert len(calls) == 1
    options, configuration, semantic_provider, provider_name, runtime_executor, baseline = calls[0]
    assert options == ScanOptions(root.resolve())
    assert configuration.resolved_policy_pack == (root / "pack.yaml").resolve()
    assert configuration.runtime.enabled is runtime_enabled
    assert configuration.runtime.airflow_version is (AirflowProfile.AIRFLOW_3_3_0 if runtime_enabled else None)
    assert (semantic_provider, provider_name) == (None, None)
    assert baseline == BaselineInput(report=expected_baseline)
    if runtime_enabled:
        assert configuration.runtime.enabled is True
        assert configuration.runtime.airflow_version is AirflowProfile.AIRFLOW_3_3_0
        assert runtime_executor is not None
    else:
        assert configuration.runtime.enabled is False
        assert runtime_executor is None


def test_runtime_image_clears_project_profile_for_core_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C07 intentionally corrects C06: an invocation image clears the project profile."""
    import conformdag.application.scan as application_scan
    import conformdag.cli as cli_module

    root = _write_gate_repo(tmp_path, with_gate=False, owner="platform")
    _write_yaml(
        root / "conformdag.yaml",
        {"config_version": "1", "runtime": {"airflow_version": "3.3.0"}},
    )
    image = "ghcr.io/example/conformdag@sha256:" + "a" * 64
    core_profiles: list[object] = []

    def scan_core(*args: object, **kwargs: object) -> ScanReport:
        core_profiles.append(kwargs["airflow_profile"])
        return _application_report()

    def fake_runtime(
        root: Path,
        config: ProjectRuntimeConfig,
        policy_ids: list[str],
        include: list[str],
        exclude: list[str],
    ) -> tuple[list[RuntimeObservation], str]:
        assert config.image == image
        assert config.airflow_version is None
        return [RuntimeObservation(status=FindingStatus.PASS, policy_id="AIR-TST-001")], image

    monkeypatch.setattr(application_scan, "scan_repository", scan_core)
    monkeypatch.setattr(cli_module, "execute_runtime", fake_runtime)

    result = CliRunner().invoke(
        app,
        [
            "scan",
            "--path",
            str(root),
            "--policy-pack",
            str(root / "pack.yaml"),
            "--runtime-image",
            image,
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.stderr
    assert core_profiles == [None]


def test_scan_resolves_once_with_invocation_relative_pack_and_selector_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import conformdag.cli as cli_module

    repository = tmp_path / "repository"
    repository.mkdir()
    root = _write_gate_repo(repository, with_gate=False, owner="platform")
    _write_yaml(
        root / "conformdag.yaml",
        {
            "config_version": "1",
            "semantic": {"base_url": "https://project.example/v1", "model": "project-model"},
        },
    )
    caller = tmp_path / "caller"
    (caller / "local").mkdir(parents=True)
    copyfile(root / "pack.yaml", caller / "local" / "pack.yaml")
    monkeypatch.chdir(caller)
    actual_resolver = resolve_effective_configuration
    resolver_calls: list[tuple[Path, ScanOverrides, Path | None]] = []

    def resolver_spy(
        repository_root: Path,
        *,
        invocation_overrides: ScanOverrides,
        invocation_working_directory: Path | None,
    ) -> EffectiveScanConfiguration:
        resolver_calls.append((repository_root, invocation_overrides, invocation_working_directory))
        return actual_resolver(
            repository_root,
            invocation_overrides=invocation_overrides,
            invocation_working_directory=invocation_working_directory,
        )

    execution_configurations: list[EffectiveScanConfiguration] = []

    def execute_service(
        options: ScanOptions,
        configuration: EffectiveScanConfiguration,
        **_kwargs: object,
    ) -> ScanExecutionResult:
        assert options == ScanOptions(root.resolve())
        execution_configurations.append(configuration)
        return ScanExecutionResult(report=_application_report(), gate_result=None)

    monkeypatch.setattr(cli_module, "resolve_effective_configuration", resolver_spy, raising=False)
    monkeypatch.setattr(cli_module, "execute_scan", execute_service)

    result = CliRunner().invoke(
        app,
        [
            "scan",
            "--path",
            str(root),
            "--policy-pack",
            "local/pack.yaml",
            "--runtime",
            "3.3.0",
            "--semantic-base-url",
            "",
            "--semantic-model",
            "",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.stderr
    assert len(resolver_calls) == 1
    resolved_root, overrides, working_directory = resolver_calls[0]
    assert resolved_root == root.resolve()
    assert overrides.policy_pack == Path("local/pack.yaml")
    assert overrides.airflow_profile is AirflowProfile.AIRFLOW_3_3_0
    assert overrides.runtime_image is None
    assert overrides.semantic_base_url is None
    assert overrides.semantic_model is None
    assert working_directory == caller.resolve()
    assert len(execution_configurations) == 1
    configuration = execution_configurations[0]
    assert configuration.resolved_policy_pack == (caller / "local" / "pack.yaml").resolve()
    assert configuration.runtime.enabled is True
    assert configuration.runtime.airflow_version is AirflowProfile.AIRFLOW_3_3_0
    assert configuration.semantic.base_url == "https://project.example/v1"
    assert configuration.semantic.model == "project-model"


def test_scan_semantic_adapter_uses_effective_values_and_api_key_at_adapter_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import conformdag.cli as cli_module

    root = _write_gate_repo(tmp_path, with_gate=False, owner="platform")
    _write_yaml(
        root / "conformdag.yaml",
        {
            "config_version": "1",
            "semantic": {
                "enabled": False,
                "base_url": "https://project.example/v1",
                "model": "project-model",
                "native_structured_output": True,
                "api_key_env": "C07_TEST_MODEL_KEY",
            },
        },
    )
    monkeypatch.setenv("C07_TEST_MODEL_KEY", "secret-c07-key")
    provider_inputs: list[tuple[str, str, str, bool]] = []
    configurations: list[EffectiveScanConfiguration] = []

    class DirectProvider:
        def __init__(
            self,
            base_url: str,
            model: str,
            api_key: str,
            *,
            native_structured_output: bool,
        ) -> None:
            provider_inputs.append((base_url, model, api_key, native_structured_output))

    class CachedProvider:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

    def fake_cache(_path: Path) -> object:
        return object()

    def execute_service(
        options: ScanOptions,
        configuration: EffectiveScanConfiguration,
        *,
        semantic_provider: SemanticProvider | None = None,
        semantic_provider_name: str | None = None,
        **_kwargs: object,
    ) -> ScanExecutionResult:
        assert options == ScanOptions(root.resolve())
        configurations.append(configuration)
        assert semantic_provider is not None
        assert semantic_provider_name == "invoke.example"
        return ScanExecutionResult(report=_application_report(), gate_result=None)

    monkeypatch.setattr(cli_module, "OpenAICompatibleProvider", DirectProvider)
    monkeypatch.setattr(cli_module, "CachedSemanticProvider", CachedProvider)
    monkeypatch.setattr(cli_module, "SemanticCache", fake_cache)
    monkeypatch.setattr(cli_module, "execute_scan", execute_service)

    result = CliRunner().invoke(
        app,
        [
            "scan",
            "--path",
            str(root),
            "--semantic",
            "--semantic-base-url",
            "https://invoke.example/v1",
            "--semantic-model",
            "invoke-model",
            "--no-semantic-structured-output",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.stderr
    assert provider_inputs == [("https://invoke.example/v1", "invoke-model", "secret-c07-key", False)]
    assert len(configurations) == 1
    configuration = configurations[0]
    assert configuration.semantic.enabled is True
    assert configuration.semantic.base_url == "https://invoke.example/v1"
    assert configuration.semantic.model == "invoke-model"
    assert configuration.semantic.native_structured_output is False
    assert "secret-c07-key" not in repr(configuration)


def test_scan_no_semantic_keeps_project_profile_inert_and_builds_no_phase_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import conformdag.cli as cli_module

    root = _write_gate_repo(tmp_path, with_gate=False, owner="platform")
    _write_yaml(
        root / "conformdag.yaml",
        {
            "config_version": "1",
            "semantic": {"enabled": True, "base_url": "https://project.example/v1", "model": "project-model"},
            "runtime": {"enabled": False, "airflow_version": "3.3.0"},
        },
    )
    configurations: list[EffectiveScanConfiguration] = []

    def unexpected_adapter(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("disabled phase adapter must not be constructed")

    def execute_service(
        options: ScanOptions,
        configuration: EffectiveScanConfiguration,
        *,
        semantic_provider: SemanticProvider | None = None,
        runtime_executor: RuntimeExecutor | None = None,
        **_kwargs: object,
    ) -> ScanExecutionResult:
        assert options == ScanOptions(root.resolve())
        configurations.append(configuration)
        assert semantic_provider is None
        assert runtime_executor is None
        return ScanExecutionResult(report=_application_report(), gate_result=None)

    monkeypatch.setattr(cli_module, "OpenAICompatibleProvider", unexpected_adapter)
    monkeypatch.setattr(cli_module, "CachedSemanticProvider", unexpected_adapter)
    monkeypatch.setattr(cli_module, "_CliRuntimeExecutor", unexpected_adapter)
    monkeypatch.setattr(cli_module, "execute_scan", execute_service)

    result = CliRunner().invoke(
        app,
        ["scan", "--path", str(root), "--no-semantic", "--format", "json"],
    )

    assert result.exit_code == 0, result.stderr
    assert len(configurations) == 1
    configuration = configurations[0]
    assert configuration.semantic.enabled is False
    assert configuration.runtime.enabled is False
    assert configuration.runtime.airflow_version is AirflowProfile.AIRFLOW_3_3_0


def test_disabled_semantic_structured_output_override_preserves_project_report_metadata(
    tmp_path: Path,
) -> None:
    root = _write_gate_repo(tmp_path, with_gate=False, owner="platform")
    _write_yaml(
        root / "conformdag.yaml",
        {"config_version": "1", "semantic": {"enabled": False, "native_structured_output": True}},
    )

    result = CliRunner().invoke(
        app,
        [
            "scan",
            "--path",
            str(root),
            "--policy-pack",
            str(root / "pack.yaml"),
            "--no-semantic",
            "--no-semantic-structured-output",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["run"]["resolved_configuration"]["semantic"]["native_structured_output"] is True


def test_scan_no_evidence_does_not_mutate_application_report_or_fingerprint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _write_gate_repo(tmp_path, with_gate=False, owner="platform")
    service_report = _application_report(include_finding=True)
    original_fingerprint = service_report.result_fingerprint
    original_evidence = service_report.findings[0].evidence
    calls: list[ScanOptions] = []

    def execute_service(
        options: ScanOptions,
        configuration: EffectiveScanConfiguration,
        *,
        semantic_provider: SemanticProvider | None = None,
        semantic_provider_name: str | None = None,
        runtime_executor: RuntimeExecutor | None = None,
        baseline: BaselineInput | None = None,
    ) -> ScanExecutionResult:
        calls.append(options)
        return ScanExecutionResult(report=service_report, gate_result=None)

    monkeypatch.setattr("conformdag.cli.execute_scan", execute_service, raising=False)

    result = CliRunner().invoke(
        app,
        ["scan", "--path", str(root), "--policy-pack", str(root / "pack.yaml"), "--no-evidence", "--format", "json"],
    )

    assert result.exit_code == 0, result.stderr
    assert len(calls) == 1
    rendered = json.loads(result.stdout)
    assert rendered["result_fingerprint"] == original_fingerprint
    assert rendered["findings"][0]["evidence"] is None
    assert service_report.result_fingerprint == original_fingerprint
    assert service_report.findings[0].evidence is original_evidence
