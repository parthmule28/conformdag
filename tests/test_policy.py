"""Policy-pack workflow tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

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
