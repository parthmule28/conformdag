"""CLI output and diagnostic routing tests."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

from ruamel.yaml import YAML
from typer.core import TyperGroup, TyperOption
from typer.main import get_command
from typer.testing import CliRunner

from conformdag.cli import app
from conformdag.models import FindingStatus, RuntimeObservation
from conformdag.runtime import RuntimePhaseError


def test_init_writes_quoted_scan_globs(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["init", "--path", str(tmp_path)])

    assert result.exit_code == 0
    config = (tmp_path / "conformdag.yaml").read_text(encoding="utf-8")
    assert '"dags/**/*.py"' in config
    assert "policy_pack: policies/pack.yaml" in config


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
