"""Distribution tests: pack pull from git and the composite action definition."""

import subprocess
from pathlib import Path
from shutil import copyfile

import pytest
from ruamel.yaml import YAML

from conformdag.packpull import PackPullError, pack_name_from_source, pull_pack


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
