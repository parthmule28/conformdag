"""Distribution tests: pack pull from git and the composite action definition."""

import re
import runpy
import subprocess
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path
from shutil import copyfile
from types import SimpleNamespace
from typing import cast

import pytest
from ruamel.yaml import YAML

from conformdag.models import AirflowProfile
from conformdag.packpull import PackPullError, pack_name_from_source, pull_pack
from conformdag.runtime import runtime_profile


def _make_pack_repository(root: Path) -> Path:
    """Create a git repository holding a validated pack with provenance."""
    for directory in ("standards", "dags", "policies"):
        (root / directory).mkdir(parents=True)
    copyfile("policies/pack.yaml", root / "policies" / "pack.yaml")
    copyfile("standards/dag-authoring.md", root / "standards" / "dag-authoring.md")
    (root / "conformdag.yaml").write_text(
        'config_version: "1"\nscan:\n  policy_pack: policies/pack.yaml\n',
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True, capture_output=True)
    for arguments in (
        ["config", "user.email", "packer@example.com"],
        ["config", "user.name", "Pack CI"],
        ["add", "-A"],
        ["commit", "-q", "-m", "org pack"],
    ):
        subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True)
    return root


def test_pull_pack_from_local_git(tmp_path: Path) -> None:
    source_repo = _make_pack_repository(tmp_path / "org-policy")
    source_repo_remote = tmp_path / "org-policy.git"
    subprocess.run(
        ["git", "clone", "-q", "--bare", str(source_repo), str(source_remote := source_repo_remote)],
        check=True,
        capture_output=True,
    )

    pulled = pull_pack(str(source_remote), cache_root=tmp_path / "cache")

    assert pulled.name == "org-policy"
    assert pulled.resolved_ref
    assert pulled.path.is_file()
    assert (tmp_path / "cache" / "org-policy").is_symlink()
    manifest_path = (tmp_path / "cache" / "org-policy") / ".conformdag-pull.yaml"
    assert manifest_path_ok(manifest_path=manifest_path, resolved_ref=pulled.resolved_ref)


def manifest_path_ok(manifest_path: Path, resolved_ref: str) -> bool:
    payload = YAML(typ="safe").load(manifest_path.read_text(encoding="utf-8"))  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    return bool(payload["resolved_ref"]) and payload["resolved_ref"] == resolved_ref


def test_pull_pack_is_idempotent_and_updates_on_repull(tmp_path: Path) -> None:
    source_repo = _make_pack_repository(tmp_path / "org")
    remote = tmp_path / "org.git"
    subprocess.run(
        ["git", "clone", "-q", "--bare", str(source_repo), str(remote)],
        check=True,
        capture_output=True,
    )
    first = pull_pack(str(remote), cache_root=tmp_path / "cache")

    second = pull_pack(str(remote), cache_root=tmp_path / "cache")

    assert first.resolved_ref == second.resolved_ref
    assert second.name == first.name


def test_pull_pack_preserves_last_known_good_on_invalid_update(tmp_path: Path) -> None:
    source_repo = _make_pack_repository(tmp_path / "org")
    remote = tmp_path / "org.git"
    subprocess.run(
        ["git", "clone", "-q", "--bare", str(source_repo), str(remote)],
        check=True,
        capture_output=True,
    )
    cache = tmp_path / "cache"
    first = pull_pack(str(remote), cache_root=cache)
    cached_pack = cache / "org" / "policies" / "pack.yaml"
    original_pack = cached_pack.read_text(encoding="utf-8")

    cached_source = source_repo / "policies" / "pack.yaml"
    cached_source.write_text("schema_version: '1'\nid: broken\nversion: '1'\npolicies: invalid\n", encoding="utf-8")
    for arguments in (
        ["add", "-A"],
        ["commit", "-q", "-m", "broken update"],
        ["push", "-q", str(remote), "HEAD:main"],
    ):
        subprocess.run(["git", *arguments], cwd=source_repo, check=True, capture_output=True)

    with pytest.raises(PackPullError, match="failed validation"):
        pull_pack(str(remote), cache_root=cache)

    assert cached_pack.read_text(encoding="utf-8") == original_pack
    assert (cache / "org" / ".conformdag-pull.yaml").read_text(encoding="utf-8").find(first.resolved_ref) >= 0


def test_pull_pack_rejects_unsafe_explicit_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from conformdag import packpull

    def unexpected_git(*_arguments: str, **_kwargs: object) -> str:
        pytest.fail("unsafe pack names must be rejected before invoking git")

    monkeypatch.setattr(packpull, "_git", unexpected_git)
    for unsafe_name in ("../escape", str(tmp_path / "escape"), "nested/name", "..", "bad name", "bad\\name"):
        with pytest.raises(PackPullError, match="name"):
            pull_pack("https://example.test/org.git", cache_root=tmp_path, name=unsafe_name)


def test_pack_git_commands_have_a_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from conformdag import packpull

    calls: list[dict[str, object]] = []

    def fake_run(_command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(packpull.subprocess, "run", fake_run)

    git = cast("Callable[..., str]", packpull.__dict__["_git"])
    assert git("status", cwd=tmp_path) == ""
    assert calls[0]["timeout"] == 120


def test_pack_name_derivation_and_reserved_schemes() -> None:
    assert pack_name_from_source("https://github.com/acme/org-policies.git") == "org-policies"
    assert pack_name_from_source("https://github.com/acme/org-policies") == "org-policies"
    with pytest.raises(PackPullError, match="reserved"):
        pack_name_from_source("platform://acme/org-policies")


def test_pull_pack_rejects_invalid_pack_and_cleans_up(tmp_path: Path) -> None:
    broken = tmp_path / "broken-src"
    broken.mkdir()
    (broken / "pack.yaml").write_text(
        "\n".join(
            [
                "schema_version: '1'",
                "id: broken",
                "version: '1'",
                "policies:",
                "  - id: AIR-BROKEN-001",
                "    title: Broken provenance",
                "    version: '1'",
                "    status: ACTIVE",
                "    severity: high",
                "    ownership: {owner: platform}",
                "    source: {document: standards/missing.md, section: 'Nope', content_hash: 0000}",
                "    invariant: something",
                "    enforcement: {type: deterministic}",
                "    configuration: {kind: required-owner}",
            ]
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=broken, check=True, capture_output=True)
    for arguments in (
        ["config", "user.email", "packer@example.com"],
        ["config", "user.name", "Pack CI"],
        ["add", "-A"],
        ["commit", "-q", "-m", "broken"],
    ):
        subprocess.run(["git", *arguments], cwd=broken, check=True, capture_output=True)
    remote = tmp_path / "broken.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(broken), str(remote)], check=True, capture_output=True)

    with pytest.raises(PackPullError, match="failed validation"):
        pull_pack(str(remote), cache_root=tmp_path / "cache")

    assert not (tmp_path / "cache" / "broken").exists()


def test_action_yml_is_a_valid_composite_action() -> None:
    action = YAML(typ="safe").load(Path("action.yml").read_text(encoding="utf-8"))  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

    assert action["runs"]["using"] == "composite"
    steps = action["runs"]["steps"]
    assert any("setup-uv" in str(step.get("uses", "")) for step in steps)
    upload = next(step for step in steps if "upload-sarif" in str(step.get("uses", "")))
    assert "sarif_file" in (upload.get("with") or {})
    blocking = steps[-1]
    assert blocking["if"] is not None and "fail-on-blocking" in str(blocking["if"])


def test_package_build_requires_the_frontend_build() -> None:
    config = tomllib.loads(Path("mise.toml").read_text(encoding="utf-8"))

    assert "ui-build" in config["tasks"]["build"]["depends"]


def test_runtime_dockerfile_excludes_overridden_airflow_constraints() -> None:
    dockerfile = Path("runtime/airflow-3.3.0/Dockerfile").read_text(encoding="utf-8")

    assert (
        "sed -E '/^(apache-airflow|apache-airflow-providers-google|google-cloud-aiplatform|"
        "GitPython|litellm|pyasn1|aiohttp|cryptography|snowflake-connector-python|"
        "snowflake-sqlalchemy|sqlparse|tornado)==/d'"
    ) in dockerfile


def test_release_workflow_uses_reviewed_sha_pins() -> None:
    uses = [
        line.split("uses:", 1)[1].strip().split(" #", 1)[0]
        for line in Path(".github/workflows/release.yml").read_text(encoding="utf-8").splitlines()
        if "uses:" in line
    ]

    assert uses
    assert all(re.fullmatch(r"[^/@]+/[^/@]+@[0-9a-f]{40}", action) for action in uses)


def test_runtime_release_check_passes_for_the_reviewed_release() -> None:
    reviewed = runtime_profile(AirflowProfile.AIRFLOW_3_3_0).reviewed_release

    result = subprocess.run(
        [sys.executable, "scripts/verify_runtime_release.py", reviewed],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"reviewed for release {reviewed}" in result.stdout


def test_runtime_release_check_fails_for_an_unreviewed_release() -> None:
    reviewed = runtime_profile(AirflowProfile.AIRFLOW_3_3_0).reviewed_release
    unreviewed = "v9.9.9-rc.999"

    result = subprocess.run(
        [sys.executable, "scripts/verify_runtime_release.py", unreviewed],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert f"refusing unreviewed release {unreviewed}" in result.stderr
    assert reviewed in result.stderr


def test_runtime_release_check_requires_a_release_ref() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/verify_runtime_release.py"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "usage: verify_runtime_release.py" in result.stderr


def test_release_workflow_gates_runtime_publish_on_review_validation() -> None:
    workflow = YAML(typ="safe").load(Path(".github/workflows/release.yml").read_text(encoding="utf-8"))  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    steps = workflow["jobs"]["runtime-images"]["steps"]

    validation = [index for index, step in enumerate(steps) if "verify_runtime_release.py" in str(step.get("run", ""))]
    assert len(validation) == 1
    step = steps[validation[0]]
    assert step["env"]["CONFORMDAG_RELEASE_REF"] == "${{ github.ref_name }}"
    publish = next(
        index for index, candidate in enumerate(steps) if "build-push-action" in str(candidate.get("uses", ""))
    )
    assert validation[0] < publish


def test_production_compose_requires_database_credentials() -> None:
    compose = YAML(typ="safe").load(Path("deploy/docker-compose.yml").read_text(encoding="utf-8"))  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    postgres_environment = compose["services"]["postgres"]["environment"]

    assert postgres_environment["POSTGRES_USER"] == "${CONFORMDAG_POSTGRES_USER:?set CONFORMDAG_POSTGRES_USER}"
    assert (
        postgres_environment["POSTGRES_PASSWORD"] == "${CONFORMDAG_POSTGRES_PASSWORD:?set CONFORMDAG_POSTGRES_PASSWORD}"
    )
    assert postgres_environment["POSTGRES_DB"] == "${CONFORMDAG_POSTGRES_DB:?set CONFORMDAG_POSTGRES_DB}"
    for service in ("api", "worker"):
        environment = compose["services"][service]["environment"]
        assert environment["CONFORMDAG_PLATFORM_DSN"] == "postgresql+psycopg://"
        assert environment["PGHOST"] == "postgres"
        assert environment["PGPORT"] == "5432"
        assert environment["PGUSER"] == "${CONFORMDAG_POSTGRES_USER:?set CONFORMDAG_POSTGRES_USER}"
        assert environment["PGPASSWORD"] == "${CONFORMDAG_POSTGRES_PASSWORD:?set CONFORMDAG_POSTGRES_PASSWORD}"
        assert environment["PGDATABASE"] == "${CONFORMDAG_POSTGRES_DB:?set CONFORMDAG_POSTGRES_DB}"
    healthcheck = compose["services"]["postgres"]["healthcheck"]["test"][1]
    assert "$${POSTGRES_USER}" in healthcheck
    assert "$${POSTGRES_DB}" in healthcheck


def test_generated_superpowers_workspace_is_ignored_without_hiding_durable_plans() -> None:
    ignored = Path(".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".superpowers/" in ignored
    assert Path("docs/superpowers/plans").is_dir()


def test_privacy_check_reports_each_unredacted_occurrence(tmp_path: Path) -> None:
    artifact = tmp_path / "report.json"
    artifact.write_text(
        '{"token": "[REDACTED]", "password": "live-password-value", "api_key": "another-key-value"}',
        encoding="utf-8",
    )

    inspect_file = cast(
        "Callable[[Path], list[str]]",
        runpy.run_path("scripts/verify_artifact_privacy.py")["inspect_file"],
    )
    issues = inspect_file(artifact)

    assert len(issues) == 2
    assert all("possible credential material" in issue for issue in issues)
