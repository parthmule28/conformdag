"""Policy-pack workflow tests."""

from __future__ import annotations

import hashlib
import importlib
import inspect
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch
from ruamel.yaml import YAML

from conformdag.bundled import community_pack_path
from conformdag.models import (
    EnforcementConfig,
    EnforcementType,
    LifecycleStatus,
    Ownership,
    Policy,
    PolicyPack,
    PolicySource,
    QualityGate,
    RequiredOwnerConfig,
    Severity,
)
from conformdag.policy import (
    PolicyValidationError,
    active_policies,
    load_policy_pack,
    load_suppressions,
    policy_contract_hash,
    policy_enforcement_hash,
    resolve_configured_policy_pack,
    resolve_policy_pack_path,
    resolve_source_document,
    select_policy_pack,
    validate_policy_pack,
    validate_policy_provenance,
)


def _policy(source: Path, policy_id: str = "AIR-DET-001", status: LifecycleStatus = LifecycleStatus.ACTIVE) -> Policy:
    content_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    return Policy(
        id=policy_id,
        title="Required owner",
        version="1.0.0",
        status=status,
        severity=Severity.HIGH,
        airflow_profiles=[],
        ownership=Ownership(owner="platform"),
        source=PolicySource(document=source, section="Owner standards", content_hash=content_hash),
        invariant="Every DAG has an owner.",
        enforcement=EnforcementConfig(type=EnforcementType.DETERMINISTIC),
        configuration=RequiredOwnerConfig(allowed_values=["platform"]),
    )


def _write_pack(path: Path, pack: PolicyPack) -> None:
    path.write_text(pack.model_dump_json(indent=2), encoding="utf-8")


def write_pack(
    tmp_path: Path,
    *,
    deterministic_checks: list[str] | None = None,
    gate_policy_ids: list[str] | None = None,
) -> Path:
    """Write one provenance-valid pack with configurable enforcement and gates."""
    standards = tmp_path / "standards" / "dag-authoring.md"
    standards.parent.mkdir(parents=True, exist_ok=True)
    standards.write_text("# DAG Authoring Standards\n\n## Ownership and metadata\n", encoding="utf-8")
    content_hash = hashlib.sha256(standards.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    pack: dict[str, Any] = {
        "schema_version": "1",
        "id": "boundary",
        "version": "1",
        "policies": [
            {
                "id": "AIR-TST-100",
                "title": "Owner policy",
                "version": "1.0.0",
                "status": "ACTIVE",
                "severity": "high",
                "airflow_profiles": ["3.3.0"],
                "ownership": {"owner": "platform"},
                "source": {
                    "document": "standards/dag-authoring.md",
                    "section": "Ownership and metadata",
                    "content_hash": content_hash,
                },
                "invariant": "Every DAG declares an owner.",
                "safe_path": "An owner is present.",
                "enforcement": {
                    "type": "deterministic",
                    "deterministic_checks": deterministic_checks
                    if deterministic_checks is not None
                    else ["effective-owner"],
                },
                "configuration": {"kind": "required-owner", "allowed_values": ["platform"]},
            }
        ],
    }
    if gate_policy_ids is not None:
        pack["quality_gates"] = [{"id": "default", "rules": [{"type": "always-block", "policy_ids": gate_policy_ids}]}]
    pack_path = tmp_path / "policies" / "pack.yaml"
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    with pack_path.open("w", encoding="utf-8") as handle:
        YAML(typ="safe").dump(pack, handle)  # pyright: ignore[reportUnknownMemberType]
    return pack_path


def test_loads_pack_and_filters_inactive_policies(tmp_path: Path) -> None:
    source = tmp_path / "standards.md"
    source.write_text("# Owner standards\nEvery DAG has an owner.\n", encoding="utf-8")
    pack_path = tmp_path / "pack.json"
    pack = PolicyPack(
        id="default",
        version="1.0.0",
        policies=[
            _policy(source),
            _policy(source, "AIR-DET-002", LifecycleStatus.CONFLICTED),
        ],
    )
    _write_pack(pack_path, pack)

    loaded = load_policy_pack(pack_path, tmp_path)

    assert len(loaded.policies) == 2
    assert [policy.id for policy in active_policies(loaded)] == ["AIR-DET-001"]


def test_rejects_stale_provenance_and_missing_section(tmp_path: Path) -> None:
    source = tmp_path / "standards.md"
    source.write_text("# Owner standards\n", encoding="utf-8")
    policy = _policy(source)
    source.write_text("# Changed standards\n", encoding="utf-8")
    pack_path = tmp_path / "pack.json"
    _write_pack(pack_path, PolicyPack(id="default", version="1.0.0", policies=[policy]))

    with pytest.raises(PolicyValidationError, match="source hash mismatch"):
        load_policy_pack(pack_path, tmp_path)


def test_load_policy_pack_rejects_unknown_deterministic_check(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path, deterministic_checks=["missing-check"])
    with pytest.raises(PolicyValidationError, match="unknown deterministic check"):
        load_policy_pack(pack_path, tmp_path)


def test_load_policy_pack_rejects_check_configuration_mismatch(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path, deterministic_checks=["effective-timeout"])
    yaml = YAML(typ="safe")
    raw = yaml.load(pack_path.read_text(encoding="utf-8"))  # pyright: ignore[reportUnknownMemberType]
    assert isinstance(raw, dict)
    raw["policies"][0]["configuration"] = {"kind": "required-owner"}
    with pack_path.open("w", encoding="utf-8") as handle:
        yaml.dump(raw, handle)  # pyright: ignore[reportUnknownMemberType]

    with pytest.raises(PolicyValidationError, match="requires configuration kind 'execution-timeout'"):
        load_policy_pack(pack_path, tmp_path)


def test_load_policy_pack_rejects_invalid_ruff_selector(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path, deterministic_checks=["ruff-air"])
    yaml = YAML(typ="safe")
    raw = yaml.load(pack_path.read_text(encoding="utf-8"))  # pyright: ignore[reportUnknownMemberType]
    assert isinstance(raw, dict)
    raw["policies"][0]["configuration"] = {"kind": "ruff-air", "rules": ["AIR*"]}
    with pack_path.open("w", encoding="utf-8") as handle:
        yaml.dump(raw, handle)  # pyright: ignore[reportUnknownMemberType]

    with pytest.raises(PolicyValidationError, match="invalid Ruff selector"):
        load_policy_pack(pack_path, tmp_path)


def test_provenance_decode_errors_are_structured_policy_failures(tmp_path: Path) -> None:
    standards = tmp_path / "standards" / "dag-authoring.md"
    standards.parent.mkdir(parents=True)
    standards.write_text("# DAG Authoring Standards\n\n## Ownership and metadata\n", encoding="utf-8")
    pack_path = write_pack(tmp_path)
    standards.write_bytes(b"\xff\xfe")

    with pytest.raises(PolicyValidationError, match="cannot read source document"):
        load_policy_pack(pack_path, tmp_path)


def test_load_policy_pack_rejects_unknown_gate_policy(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path, gate_policy_ids=["AIR-MISSING-001"])
    with pytest.raises(PolicyValidationError, match="unknown policy ids"):
        load_policy_pack(pack_path, tmp_path)


def test_rejects_duplicate_policy_ids() -> None:
    with pytest.raises(ValueError, match="policy IDs must be unique"):
        PolicyPack.model_validate(
            {
                "id": "default",
                "version": "1.0.0",
                "policies": [
                    {
                        "id": "AIR-DET-001",
                        "title": "one",
                        "version": "1.0.0",
                        "status": "ACTIVE",
                        "severity": "high",
                        "ownership": {"owner": "platform"},
                        "source": {
                            "document": "standards.md",
                            "section": "Owner",
                            "content_hash": "x",
                        },
                        "invariant": "x",
                        "enforcement": {"type": "deterministic"},
                        "configuration": {"kind": "required-owner"},
                    },
                    {
                        "id": "AIR-DET-001",
                        "title": "two",
                        "version": "1.0.0",
                        "status": "ACTIVE",
                        "severity": "high",
                        "ownership": {"owner": "platform"},
                        "source": {
                            "document": "standards.md",
                            "section": "Owner",
                            "content_hash": "x",
                        },
                        "invariant": "x",
                        "enforcement": {"type": "deterministic"},
                        "configuration": {"kind": "required-owner"},
                    },
                ],
            }
        )


def test_loads_external_suppressions(tmp_path: Path) -> None:
    suppressions = tmp_path / "suppressions.yaml"
    suppressions.write_text(
        "suppressions:\n"
        "  - fingerprint: abc\n"
        "    policy_id: AIR-DET-001\n"
        "    reason: migration\n"
        "    owner: platform\n"
        "    created_at: 2026-01-01T00:00:00Z\n"
        "    expires_at: 2026-12-31T00:00:00Z\n",
        encoding="utf-8",
    )

    loaded = load_suppressions(suppressions)

    assert loaded[0].fingerprint == "abc"


def test_rejects_ambiguous_implicit_pack_selection(tmp_path: Path) -> None:
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "one.yaml").write_text("{}\n", encoding="utf-8")
    (policies / "two.yaml").write_text("{}\n", encoding="utf-8")

    with pytest.raises(PolicyValidationError, match="exactly one policy pack"):
        select_policy_pack(None, tmp_path)


def test_resolve_policy_pack_path_from_working_directory(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    pack = tmp_path / "policies" / "pack.yaml"
    pack.parent.mkdir(parents=True)
    pack.write_text('schema_version: "1"\nid: default\nversion: 1.0.0\npolicies: []\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    resolved = resolve_policy_pack_path(Path("policies/pack.yaml"))

    assert resolved == pack.resolve()


def test_resolve_configured_policy_pack_uses_scan_root_for_project_defaults(tmp_path: Path) -> None:
    scan_root = tmp_path / "airflow-repo"
    pack = scan_root / "policies" / "pack.yaml"
    pack.parent.mkdir(parents=True)
    pack.write_text('schema_version: "1"\nid: default\nversion: 1.0.0\npolicies: []\n', encoding="utf-8")

    resolved = resolve_configured_policy_pack(
        Path("policies/pack.yaml"),
        scan_root=scan_root,
        from_cli=False,
    )

    assert resolved == pack.resolve()


def test_resolve_policy_pack_path_accepts_community_alias() -> None:
    from conformdag.bundled import community_pack_path

    resolved = resolve_policy_pack_path(Path("community"))

    assert resolved == community_pack_path()


def test_resolve_configured_policy_pack_accepts_community_alias_from_cli(
    tmp_path: Path,
) -> None:
    from conformdag.bundled import community_pack_path

    resolved = resolve_configured_policy_pack(
        Path("community"),
        scan_root=tmp_path / "foreign-airflow",
        from_cli=True,
    )

    assert resolved == community_pack_path()


def test_bundled_community_pack_loads_with_pack_local_provenance() -> None:
    from conformdag.bundled import community_pack_path

    loaded = load_policy_pack(community_pack_path(), Path.cwd())

    assert loaded.id == "conformdag-community"
    assert [policy.id for policy in loaded.policies] == [
        "COM-DET-001",
        "COM-DET-002",
        "COM-DET-003",
    ]


def test_resolve_source_document_from_pack_tree(tmp_path: Path) -> None:
    pack_dir = tmp_path / "bundled" / "policies"
    pack_dir.mkdir(parents=True)
    standards = tmp_path / "bundled" / "standards" / "rules.md"
    standards.parent.mkdir(parents=True)
    standards.write_text("# Owner standards\nEvery DAG has an owner.\n", encoding="utf-8")
    pack_path = pack_dir / "pack.yaml"
    pack_path.write_text("policies: []\n", encoding="utf-8")
    scan_root = tmp_path / "foreign-airflow"
    scan_root.mkdir()

    resolved = resolve_source_document(
        Path("standards/rules.md"),
        pack_path=pack_path,
        repository_root=scan_root,
    )

    assert resolved == standards.resolve()


def test_loads_pack_provenance_without_copying_standards_into_scan_root(tmp_path: Path) -> None:
    pack_root = tmp_path / "conformdag"
    standards = pack_root / "standards" / "dag-authoring.md"
    standards.parent.mkdir(parents=True)
    standards.write_text("# Owner standards\nEvery DAG has an owner.\n", encoding="utf-8")
    pack_path = pack_root / "policies" / "pack.yaml"
    pack_path.parent.mkdir(parents=True)
    content_hash = hashlib.sha256(standards.read_bytes()).hexdigest()
    pack = PolicyPack(
        id="default",
        version="1.0.0",
        policies=[
            Policy(
                id="AIR-DET-001",
                title="Required owner",
                version="1.0.0",
                status=LifecycleStatus.ACTIVE,
                severity=Severity.HIGH,
                airflow_profiles=[],
                ownership=Ownership(owner="platform"),
                source=PolicySource(
                    document=Path("standards/dag-authoring.md"),
                    section="Owner standards",
                    content_hash=content_hash,
                ),
                invariant="Every DAG has an owner.",
                enforcement=EnforcementConfig(type=EnforcementType.DETERMINISTIC),
                configuration=RequiredOwnerConfig(allowed_values=["platform"]),
            )
        ],
    )
    _write_pack(pack_path, pack)
    scan_root = tmp_path / "foreign-airflow"
    scan_root.mkdir()

    loaded = load_policy_pack(pack_path, scan_root)

    assert loaded.policies[0].id == "AIR-DET-001"


def test_policy_package_facade_reexports_all_public_implementations() -> None:
    policy_module = importlib.import_module("conformdag.policy")
    implementations = {
        "PolicyValidationError": "conformdag.policy.loading",
        "resolve_policy_pack_path": "conformdag.policy.loading",
        "resolve_configured_policy_pack": "conformdag.policy.loading",
        "load_policy_pack": "conformdag.policy.loading",
        "select_policy_pack": "conformdag.policy.loading",
        "load_suppressions": "conformdag.policy.loading",
        "resolve_source_document": "conformdag.policy.provenance",
        "validate_policy_provenance": "conformdag.policy.provenance",
        "validate_policy_pack": "conformdag.policy.validation",
        "active_policies": "conformdag.policy.validation",
        "policy_contract_hash": "conformdag.policy.hashes",
        "policy_enforcement_hash": "conformdag.policy.hashes",
    }

    for name, module_name in implementations.items():
        try:
            implementation = getattr(importlib.import_module(module_name), name)
        except ModuleNotFoundError as exc:
            pytest.fail(f"expected package implementation {module_name}.{name} to import: {exc}")
        assert getattr(policy_module, name) is implementation


def test_policy_public_callable_signatures_are_preserved() -> None:
    from conformdag import policy

    expected = {
        "PolicyValidationError": "(issues: 'list[str]') -> 'None'",
        "active_policies": "(pack: 'PolicyPack') -> 'list[Policy]'",
        "load_policy_pack": "(path: 'Path', repository_root: 'Path | None' = None) -> 'PolicyPack'",
        "load_suppressions": "(path: 'Path') -> 'list[Suppression]'",
        "policy_contract_hash": "(policy: 'Policy') -> 'str'",
        "policy_enforcement_hash": "(policy: 'Policy') -> 'str'",
        "resolve_configured_policy_pack": "(configured: 'Path', *, scan_root: 'Path', from_cli: 'bool', working_directory: 'Path | None' = None) -> 'Path'",
        "resolve_policy_pack_path": "(path: 'Path', *, working_directory: 'Path | None' = None) -> 'Path'",
        "resolve_source_document": "(document: 'Path', *, pack_path: 'Path', repository_root: 'Path') -> 'Path'",
        "select_policy_pack": "(path: 'Path | None', repository_root: 'Path') -> 'PolicyPack'",
        "validate_policy_pack": "(pack: 'PolicyPack') -> 'list[str]'",
        "validate_policy_provenance": "(pack: 'PolicyPack', *, pack_path: 'Path', repository_root: 'Path') -> 'list[str]'",
    }

    assert {name: str(inspect.signature(getattr(policy, name))) for name in expected} == expected


def test_policy_validation_error_preserves_value_error_contract() -> None:
    issues = ["first issue", "second issue"]

    error = PolicyValidationError(issues)

    assert isinstance(error, ValueError)
    assert error.issues is issues
    assert str(error) == "first issue; second issue"


def test_policy_loader_wraps_yaml_and_filesystem_errors(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.yaml"
    malformed.write_text("policies: [unterminated\n", encoding="utf-8")

    with pytest.raises(PolicyValidationError) as yaml_error:
        load_policy_pack(malformed)

    assert len(yaml_error.value.issues) == 1
    assert yaml_error.value.issues[0].startswith(f"invalid YAML in {malformed}:")
    assert str(yaml_error.value) == yaml_error.value.issues[0]

    missing = tmp_path / "missing.yaml"
    with pytest.raises(PolicyValidationError) as missing_error:
        load_policy_pack(missing)

    assert len(missing_error.value.issues) == 1
    assert missing_error.value.issues[0].startswith(f"cannot read {missing}:")


@pytest.mark.parametrize("alias", ["community", "builtin:community"])
def test_bundled_aliases_resolve_through_cli_and_project_configuration(alias: str, tmp_path: Path) -> None:
    expected = community_pack_path()

    assert resolve_policy_pack_path(Path(alias)) == expected
    assert (
        resolve_configured_policy_pack(
            Path(alias), scan_root=tmp_path / "repository", from_cli=True, working_directory=tmp_path
        )
        == expected
    )
    assert resolve_configured_policy_pack(Path(alias), scan_root=tmp_path / "repository", from_cli=False) == expected


def test_policy_selection_loads_a_single_candidate_and_reports_ambiguity(tmp_path: Path) -> None:
    policies = tmp_path / "policies"
    policies.mkdir()
    one = policies / "one.yaml"
    one.write_text("schema_version: '1'\nid: one\nversion: '1'\npolicies: []\n", encoding="utf-8")

    assert select_policy_pack(None, tmp_path).id == "one"

    two = policies / "two.yml"
    two.write_text("schema_version: '1'\nid: two\nversion: '1'\npolicies: []\n", encoding="utf-8")
    with pytest.raises(PolicyValidationError) as ambiguity:
        select_policy_pack(None, tmp_path)

    assert ambiguity.value.issues == [f"exactly one policy pack must be selected; found 2 candidates under {policies}"]


def test_source_resolution_uses_pack_then_parent_then_repository_candidates(tmp_path: Path) -> None:
    pack_path = tmp_path / "pack-root" / "policies" / "pack.yaml"
    repository_root = tmp_path / "scan-root"
    document = Path("standards/rules.md")
    candidates = [
        pack_path.parent / document,
        pack_path.parent.parent / document,
        repository_root / document,
    ]
    for index, candidate in enumerate(candidates):
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text(f"candidate {index}\n", encoding="utf-8")

    def resolve() -> Path:
        return resolve_source_document(document, pack_path=pack_path, repository_root=repository_root)

    assert resolve() == candidates[0].resolve()
    candidates[0].unlink()
    assert resolve() == candidates[1].resolve()
    candidates[1].unlink()
    assert resolve() == candidates[2].resolve()
    candidates[2].unlink()
    assert resolve() == (repository_root / document).resolve()


def test_provenance_reports_missing_section_then_content_hash_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "standards.md"
    source.write_text("A document without the required heading.\n", encoding="utf-8")
    policy = _policy(source)
    policy = policy.model_copy(
        update={"source": policy.source.model_copy(update={"section": "Missing heading", "content_hash": "0" * 64})}
    )
    pack = PolicyPack(id="test", version="1", policies=[policy])
    source_path = source.resolve()
    actual_hash = hashlib.sha256(source.read_bytes()).hexdigest()

    issues = validate_policy_provenance(pack, pack_path=tmp_path / "policies" / "pack.yaml", repository_root=tmp_path)

    assert issues == [
        f"AIR-DET-001: source section 'Missing heading' was not found in {source_path}",
        f"AIR-DET-001: source hash mismatch for {source_path} (expected {'0' * 64}, got {actual_hash})",
    ]


def test_policy_validation_preserves_issue_contents_and_order(tmp_path: Path) -> None:
    source = tmp_path / "standards.md"
    source.write_text("Owner standards\n", encoding="utf-8")
    policy = Policy(
        id="AIR-TST-100",
        title="Owner policy",
        version="1.0.0",
        status=LifecycleStatus.ACTIVE,
        severity=Severity.HIGH,
        airflow_profiles=[],
        ownership=Ownership(owner="platform"),
        source=PolicySource(
            document=source, section="Owner standards", content_hash=hashlib.sha256(source.read_bytes()).hexdigest()
        ),
        invariant="Every DAG declares an owner.",
        enforcement=EnforcementConfig(
            type=EnforcementType.DETERMINISTIC,
            deterministic_checks=["effective-timeout", "missing-check"],
        ),
        configuration=RequiredOwnerConfig(allowed_values=["platform"]),
    )
    gates = [
        QualityGate.model_validate(
            {"id": "duplicate", "rules": [{"type": "always-block", "policy_ids": ["AIR-UNKNOWN-002"]}]}
        ),
        QualityGate.model_validate(
            {"id": "duplicate", "rules": [{"type": "always-block", "policy_ids": ["AIR-UNKNOWN-001"]}]}
        ),
    ]
    pack = PolicyPack(id="test", version="1", policies=[policy], quality_gates=gates)

    assert validate_policy_pack(pack) == [
        "quality gate ids must be unique within a pack",
        "gate 'duplicate' references unknown policy ids: AIR-UNKNOWN-002",
        "gate 'duplicate' references unknown policy ids: AIR-UNKNOWN-001",
        "AIR-TST-100: deterministic check 'effective-timeout' requires configuration kind 'execution-timeout', got 'required-owner'",
        "AIR-TST-100: unknown deterministic check 'missing-check'",
    ]


def test_suppression_loader_accepts_lists_mappings_empty_and_missing_files(tmp_path: Path) -> None:
    suppression = (
        "fingerprint: abc\n"
        "policy_id: AIR-DET-001\n"
        "reason: migration\n"
        "owner: platform\n"
        "created_at: 2026-01-01T00:00:00Z\n"
        "expires_at: 2026-12-31T00:00:00Z\n"
    )
    list_file = tmp_path / "list.yaml"
    list_file.write_text(f"- {suppression.replace(chr(10), chr(10) + '  ').lstrip()}\n", encoding="utf-8")
    mapping_file = tmp_path / "mapping.yaml"
    mapping_file.write_text(
        f"suppressions:\n  - {suppression.replace(chr(10), chr(10) + '    ').lstrip()}\n", encoding="utf-8"
    )
    empty_file = tmp_path / "empty.yaml"
    empty_file.write_text("\n", encoding="utf-8")
    empty_mapping_file = tmp_path / "empty-mapping.yaml"
    empty_mapping_file.write_text("other: []\n", encoding="utf-8")

    assert load_suppressions(tmp_path / "missing.yaml") == []
    assert load_suppressions(empty_file) == []
    assert load_suppressions(empty_mapping_file) == []
    assert [item.fingerprint for item in load_suppressions(list_file)] == ["abc"]
    assert [item.fingerprint for item in load_suppressions(mapping_file)] == ["abc"]


def test_policy_hashes_match_pre_extraction_golden_digests() -> None:
    golden = {
        "AIR-DET-001": (
            "660304d1be4d2807c875865592f2743f324296a5a6e10425c3c33a736f1ccacb",
            "f391189d15da4a6079d9192095b7f1acefedb5538ae1d55be5f53d438b31dd68",
        ),
        "AIR-DET-002": (
            "167ef163ab255f530e8af1570dc165375064464cbb98651101726cef2974ebd5",
            "44e04992b82730600a4a55d6b8e40e513ba5f06df999991b9bc3431f9905db0c",
        ),
        "AIR-DET-003": (
            "9524c045d67666310ce454ca8db7e36f48df8637ce7b5e84c6928f636ef4442d",
            "c18634845f49dc07bb821c5ab23ca404a2ebfdd98a9ca3f63e2c0518180bf8d6",
        ),
        "AIR-DET-004": (
            "60b73bc710fde267e50b0aaa15c3e06110ec25d1f60df879ce52cc9be7bfb703",
            "583a498b21b2c672e3e5b7b5b1d3aed3d9160c3dc4ed09d74fc47c2dc787ac93",
        ),
        "AIR-DET-005": (
            "ef1c64e73728be96339c4c9ba6d36b81b50f1739422d806a3d480a2fc3747f0f",
            "8a57ded5eaaaf52213721947ee3d06c10dab01be2ccda7f18b25709abafcd907",
        ),
        "AIR-DET-006": (
            "b3e0356e544544ace6415809c53aea3abac3d90e07702c8febe3937015cea4dc",
            "218e8c5851f9d47abb32f73b94b7f8a0f409bd713eff69692e63ea68ca396020",
        ),
        "AIR-DET-007": (
            "bed617d1f32a9319126c4860db3d3e5a653681aea0e38396117bad0b240a35ac",
            "e605396e6d21b846c66855f892814f138d864ef349769ab0776184dc2952bcb5",
        ),
        "AIR-DET-008": (
            "7222297b7fbf384b7c67427d97f6ccd04f0e32ee7a6532be47f17dd3b181f163",
            "4438898f8e0072119c2aa1dc9d2b07e7fa9fe2dc971e2a0a065ef5aaa9f2db9a",
        ),
        "AIR-DET-009": (
            "974d7845ad5be0428ccc486f824394e244a61778dcd21924b676142623a76228",
            "077f165ac1da25d2135bded1ebb924be6db90c515033904b50eef6be8fe890de",
        ),
        "AIR-DET-011": (
            "db5acf61f41f93e3a233ba80b1671ff71d5d400e8c82e55b16ef481e27ba77ea",
            "33861842c2226a2322686ee4ecc13427ee1eb415c0f38091bc8cc79018df3a77",
        ),
        "AIR-SEM-001": (
            "2d5e08a7ff4711740bb1899d6d14d017a4ed701ebd39207933ac9bfe188287c4",
            "698fad0a53df1edd5e33227681c4fefcd7cddda861a51f358978da035c2bc12c",
        ),
        "AIR-SEM-002": (
            "cd2ba28cc3703f60c88bae20c27cf21e9fff6a39a3fd33a3c28726ededab62d8",
            "698fad0a53df1edd5e33227681c4fefcd7cddda861a51f358978da035c2bc12c",
        ),
        "AIR-SEM-003": (
            "9bfa2541c5ff035b53e54f63c0aa6aa749baf24b4667e2a1dadda502fe04f9ea",
            "da81541e362f865dacc40f98d6c1ba801999ad679e809fc64ed95635257d3667",
        ),
        "AIR-SEM-004": (
            "29a0f136d75577d385184b7d6dc298f07a0e49f68a8e4d5c96af63c15c043205",
            "698fad0a53df1edd5e33227681c4fefcd7cddda861a51f358978da035c2bc12c",
        ),
        "COM-DET-001": (
            "3053f0985d7f88c1a687340d55a13d744dde742ca61058b2c19639994168d280",
            "c18634845f49dc07bb821c5ab23ca404a2ebfdd98a9ca3f63e2c0518180bf8d6",
        ),
        "COM-DET-002": (
            "69413db824d0d51691473a963124ee7210ce92082155a655b3c75247b3cb5fc3",
            "583a498b21b2c672e3e5b7b5b1d3aed3d9160c3dc4ed09d74fc47c2dc787ac93",
        ),
        "COM-DET-003": (
            "08eeda06a17cde7dac2c1f3b3fc8089f57b3b43ea4c26668f740c50fc5b53185",
            "8a57ded5eaaaf52213721947ee3d06c10dab01be2ccda7f18b25709abafcd907",
        ),
    }
    packs = [
        load_policy_pack(Path("policies/pack.yaml"), Path.cwd()),
        load_policy_pack(community_pack_path(), Path.cwd()),
    ]

    actual = {
        policy.id: (policy_contract_hash(policy), policy_enforcement_hash(policy))
        for pack in packs
        for policy in pack.policies
    }

    assert actual == golden


def test_policy_package_import_has_no_cycles_or_repository_side_effects(tmp_path: Path) -> None:
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "pack.yaml").write_text("malformed: [yaml\n", encoding="utf-8")
    dags = tmp_path / "dags"
    dags.mkdir()
    (dags / "untrusted.py").write_text(
        "from pathlib import Path\nPath('executed.marker').write_text('executed')\n", encoding="utf-8"
    )
    script = """
import importlib
import socket
import subprocess
import sys
from pathlib import Path

def forbidden(*args, **kwargs):
    raise AssertionError("policy import caused an external or repository side effect")

socket.socket = forbidden
subprocess.Popen = forbidden
subprocess.run = forbidden
original_open = Path.open
pack_path = (Path.cwd() / "policies" / "pack.yaml").resolve()
def guarded_open(self, mode="r", *args, **kwargs):
    if self.resolve() == pack_path or any(flag in mode for flag in "wax+"):
        raise AssertionError(f"unexpected policy import file access: {self} ({mode})")
    return original_open(self, mode, *args, **kwargs)
Path.open = guarded_open
before = set(Path.cwd().iterdir())
for module in (
    "conformdag.policy",
    "conformdag.policy.loading",
    "conformdag.policy.provenance",
    "conformdag.policy.validation",
    "conformdag.policy.hashes",
):
    importlib.import_module(module)
assert "conformdag.platform" not in sys.modules
assert set(Path.cwd().iterdir()) == before
assert not Path("executed.marker").exists()
"""
    child_env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("COV_CORE_") and key != "COVERAGE_PROCESS_START"
    }

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=child_env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
