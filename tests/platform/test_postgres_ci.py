"""Offline contract checks for the mandatory PostgreSQL CI job."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from ruamel.yaml import YAML

_POSTGRES_TEST_PASSWORD = "c26-ephemeral-postgres-test-only"


def _assert_postgres_job_conditions(job: object) -> None:
    """Disallow job/step gates except the explicit always-run cleanup audit."""
    job_mapping = cast("Mapping[str, object]", job)
    assert "if" not in job_mapping
    assert "continue-on-error" not in job_mapping

    steps = cast("list[object]", job_mapping["steps"])
    cleanup_count = 0
    for raw_step in steps:
        step = cast("Mapping[str, object]", raw_step)
        if step.get("name") == "Verify PostgreSQL test cleanup":
            cleanup_count += 1
            assert step.get("if") == "${{ always() }}"
            assert "continue-on-error" not in step
        else:
            assert "if" not in step
            assert "continue-on-error" not in step
    assert cleanup_count == 1


def _assert_postgres_passwords_are_test_only(job: object) -> None:
    """Keep the ephemeral CI database credential independent of GitHub tokens."""
    job_mapping = cast("Mapping[str, object]", job)
    services = cast("Mapping[str, object]", job_mapping["services"])
    postgres_service = cast("Mapping[str, object]", services["postgres"])
    service_env = cast("Mapping[str, object]", postgres_service["env"])
    steps = cast("list[object]", job_mapping["steps"])
    named_steps = {cast("Mapping[str, object]", step).get("name"): cast("Mapping[str, object]", step) for step in steps}
    setup_env = cast("Mapping[str, object]", named_steps["Configure PostgreSQL test DSN"]["env"])
    cleanup_env = cast("Mapping[str, object]", named_steps["Verify PostgreSQL test cleanup"]["env"])
    passwords = (
        service_env["POSTGRES_PASSWORD"],
        setup_env["POSTGRES_SUPERUSER_PASSWORD"],
        cleanup_env["POSTGRES_SUPERUSER_PASSWORD"],
    )

    for password in passwords:
        assert isinstance(password, str)
        assert "${{" not in password
        assert password == _POSTGRES_TEST_PASSWORD


def test_postgres_ci_job_is_mandatory_isolated_and_repeated() -> None:
    workflow = YAML(typ="safe").load(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    jobs = workflow["jobs"]

    assert {"fast", "frontend-e2e", "benchmark", "release-validation", "host-macos", "runtime"} <= set(jobs)
    assert jobs["semantic-smoke"]["if"] == "${{ vars.CONFORMDAG_RUN_SEMANTIC_SMOKE == 'true' }}"

    job = jobs["postgres-integration"]
    assert job["name"] == "PostgreSQL integration"
    assert job["runs-on"] == "ubuntu-latest"
    assert 0 < job["timeout-minutes"] <= 30
    assert job["permissions"]["contents"] == "read"
    _assert_postgres_job_conditions(job)

    service = job["services"]["postgres"]
    assert service["image"] == "postgres:17-alpine"
    assert service["env"]["POSTGRES_USER"] == "postgres"
    _assert_postgres_passwords_are_test_only(job)
    assert service["env"]["POSTGRES_DB"] == "postgres"
    assert service["ports"] == ["127.0.0.1:5432:5432"]
    assert "--health-cmd" in service["options"]
    assert "pg_isready" in service["options"]
    assert "--health-interval 5s" in service["options"]
    assert "--health-timeout 5s" in service["options"]
    assert "--health-retries 10" in service["options"]

    steps = job["steps"]
    assert any(step.get("run") == "mise run setup" for step in steps)
    postgres_runs = [step for step in steps if step.get("run") == "mise run test:postgres"]
    assert len(postgres_runs) == 2
    assert postgres_runs[0] is not postgres_runs[1]

    setup_dsn = next(step for step in steps if step.get("name") == "Configure PostgreSQL test DSN")
    assert "uv run python - <<'PY'" in setup_dsn["run"]
    assert "GITHUB_ENV" in setup_dsn["run"]
    assert "add-mask" in setup_dsn["run"]
    assert "CREATE ROLE" in setup_dsn["run"]
    assert "sql.Identifier" in setup_dsn["run"]
    assert "sql.Literal" in setup_dsn["run"]

    cleanup = next(step for step in steps if step.get("name") == "Verify PostgreSQL test cleanup")
    assert cleanup["if"] == "${{ always() }}"
    assert "uv run python - <<'PY'" in cleanup["run"]
    assert "pg_database" in cleanup["run"]
    assert "pg_stat_activity" in cleanup["run"]
    assert "default_transaction_read_only=on" in cleanup["run"]
    assert "DROP DATABASE" not in cleanup["run"].upper()


@pytest.mark.parametrize("location", ["service", "setup", "cleanup"])
@pytest.mark.parametrize("expression", ["${{ github.token }}", "${{ secrets.GITHUB_TOKEN }}"])
def test_postgres_ci_password_guard_rejects_github_tokens(location: str, expression: str) -> None:
    workflow = YAML(typ="safe").load(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    job = deepcopy(workflow["jobs"]["postgres-integration"])
    steps = job["steps"]

    if location == "service":
        job["services"]["postgres"]["env"]["POSTGRES_PASSWORD"] = expression
    else:
        step_name = "Configure PostgreSQL test DSN" if location == "setup" else "Verify PostgreSQL test cleanup"
        target_step = next(step for step in steps if step.get("name") == step_name)
        target_step["env"]["POSTGRES_SUPERUSER_PASSWORD"] = expression

    with pytest.raises(AssertionError):
        _assert_postgres_passwords_are_test_only(job)


@pytest.mark.parametrize(
    ("target", "condition", "value"),
    [
        ("job", "if", "${{ github.ref == 'refs/heads/main' }}"),
        ("job", "continue-on-error", "${{ github.event_name == 'pull_request' }}"),
        ("suite", "if", "${{ always() }}"),
        ("suite", "continue-on-error", "${{ failure() }}"),
        ("cleanup", "if", "${{ success() }}"),
        ("cleanup", "continue-on-error", "${{ true }}"),
    ],
)
def test_postgres_ci_condition_guard_rejects_unapproved_expressions(target: str, condition: str, value: str) -> None:
    workflow = YAML(typ="safe").load(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    job = deepcopy(workflow["jobs"]["postgres-integration"])

    if target == "job":
        job[condition] = value
    else:
        step_name = (
            "Verify PostgreSQL test cleanup" if target == "cleanup" else "PostgreSQL integration suite (first run)"
        )
        target_step = next(step for step in job["steps"] if step.get("name") == step_name)
        target_step[condition] = value

    with pytest.raises(AssertionError):
        _assert_postgres_job_conditions(job)
