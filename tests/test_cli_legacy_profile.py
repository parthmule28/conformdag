"""Tests for removal of unsupported beta runtime profiles."""

from typer.testing import CliRunner

from conformdag.cli import app


def test_removed_legacy_runtime_profile_is_rejected() -> None:
    result = CliRunner().invoke(app, ["scan", "--path", ".", "--runtime", "2.11.2"])

    assert result.exit_code == 2
    assert "Invalid value" in result.output
