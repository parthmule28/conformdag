"""Policy-pack workflow tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from conformdag.models import (
    EnforcementConfig,
    EnforcementType,
    LifecycleStatus,
    Ownership,
    Policy,
    PolicyPack,
    PolicySource,
    RequiredOwnerConfig,
    Severity,
)
from conformdag.policy import (
    PolicyValidationError,
    active_policies,
    load_policy_pack,
    load_suppressions,
    resolve_configured_policy_pack,
    resolve_policy_pack_path,
    resolve_source_document,
    select_policy_pack,
)


def _policy(
    source: Path, policy_id: str = "AIR-DET-001", status: LifecycleStatus = LifecycleStatus.ACTIVE
) -> Policy:
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


def test_resolve_policy_pack_path_from_working_directory(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    pack = tmp_path / "policies" / "pack.yaml"
    pack.parent.mkdir(parents=True)
    pack.write_text(
        'schema_version: "1"\nid: default\nversion: 1.0.0\npolicies: []\n', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    resolved = resolve_policy_pack_path(Path("policies/pack.yaml"))

    assert resolved == pack.resolve()


def test_resolve_configured_policy_pack_uses_scan_root_for_project_defaults(tmp_path: Path) -> None:
    scan_root = tmp_path / "airflow-repo"
    pack = scan_root / "policies" / "pack.yaml"
    pack.parent.mkdir(parents=True)
    pack.write_text(
        'schema_version: "1"\nid: default\nversion: 1.0.0\npolicies: []\n', encoding="utf-8"
    )

    resolved = resolve_configured_policy_pack(
        Path("policies/pack.yaml"),
        scan_root=scan_root,
        from_cli=False,
    )

    assert resolved == pack.resolve()


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
