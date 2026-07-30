"""CLI output and diagnostic routing tests."""

import json

from typer.testing import CliRunner

from conformdag.cli import app


def test_terminal_scan_output_is_human_readable() -> None:
    result = CliRunner().invoke(app, ["scan", "--path", ".", "--format", "terminal"])

    assert result.exit_code == 0
    assert "ConformDAG scan complete" in result.stdout
    assert "Result fingerprint:" in result.stdout


def test_html_scan_requires_an_explicit_destination() -> None:
    result = CliRunner().invoke(app, ["scan", "--path", ".", "--format", "html"])

    assert result.exit_code == 2
    assert "HTML output requires --output" in result.output


def test_preview_model_context_is_local_and_provider_free() -> None:
    result = CliRunner().invoke(app, ["scan", "--path", ".", "--preview-model-context"])

    assert result.exit_code == 0
    assert '"context_hash"' in result.stdout
    assert '"redacted_context"' in result.stdout


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
