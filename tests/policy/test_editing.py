"""Tests for transport-independent policy and gate editing."""

from __future__ import annotations

import hashlib
from pathlib import Path
from shutil import copyfile
from typing import Any, cast

import pytest
from ruamel.yaml import YAML

from conformdag.models import Policy, PolicyPack
from conformdag.policy import load_policy_pack
from conformdag.policy.editing import (
    PolicyEditingError,
    PolicyMemberNotFoundError,
    PolicyMutation,
    delete_gate,
    delete_policy,
    upsert_gate,
    upsert_policy,
)


def _write_fixture_pack(tmp_path: Path) -> tuple[Path, Path]:
    pack_path = tmp_path / "policies" / "pack.yaml"
    pack_path.parent.mkdir(parents=True)
    source_path = tmp_path / "standards" / "dag-authoring.md"
    source_path.parent.mkdir(parents=True)
    copyfile("policies/pack.yaml", pack_path)
    copyfile("standards/dag-authoring.md", source_path)
    return pack_path, source_path


def _set_gates(pack_path: Path, gates: list[dict[str, Any]]) -> None:
    yaml = YAML(typ="safe")
    raw = yaml.load(pack_path.read_text(encoding="utf-8"))  # pyright: ignore[reportUnknownMemberType]
    pack_data = cast("dict[str, Any]", raw)
    pack_data["quality_gates"] = gates
    with pack_path.open("w", encoding="utf-8") as stream:
        yaml.dump(pack_data, stream)  # pyright: ignore[reportUnknownMemberType]


def _policy_mutation(source_document: str = "standards/dag-authoring.md") -> PolicyMutation:
    return {
        "title": "Updated owner policy",
        "version": "2.0.0",
        "status": "ACTIVE",
        "severity": "high",
        "source_document": source_document,
        "source_section": "Ownership and metadata",
        "invariant": "Every DAG declares an approved owner.",
    }


def _policies(pack: PolicyPack) -> dict[str, Policy]:
    return {policy.id: policy for policy in pack.policies}


def test_upsert_policy_refreshes_source_hash_and_preserves_omitted_metadata(tmp_path: Path) -> None:
    pack_path, _ = _write_fixture_pack(tmp_path)
    before = _policies(load_policy_pack(pack_path, tmp_path))["AIR-DET-001"]
    new_source = tmp_path / "standards" / "new-standard.md"
    new_source.write_text("# New Standard\n\n## Owner Policy\nOwners are recorded.\n", encoding="utf-8")
    mutation = _policy_mutation("standards/new-standard.md")
    mutation["source_section"] = "Owner Policy"

    saved = upsert_policy(pack_path, "AIR-DET-001", mutation)

    assert isinstance(saved, PolicyPack)
    updated = _policies(load_policy_pack(pack_path, tmp_path))["AIR-DET-001"]
    assert updated.title == "Updated owner policy"
    assert str(updated.source.document) == "standards/new-standard.md"
    assert updated.source.section == "Owner Policy"
    assert updated.source.content_hash == hashlib.sha256(new_source.read_bytes()).hexdigest()
    assert updated.source.version == before.source.version
    for field in ("ownership", "scope", "exceptions", "enforcement", "configuration", "tags", "safe_path"):
        assert getattr(updated, field) == getattr(before, field)


def test_upsert_policy_requires_complete_metadata_for_new_policy(tmp_path: Path) -> None:
    pack_path, _ = _write_fixture_pack(tmp_path)
    before = pack_path.read_bytes()
    mutation = _policy_mutation()

    with pytest.raises(PolicyEditingError, match="requires complete contract metadata"):
        upsert_policy(pack_path, "AIR-NEW-001", mutation)

    assert pack_path.read_bytes() == before
    mutation.update(
        {
            "ownership": {"owner": "platform"},
            "scope": {"files": ["dags/**/*.py"], "operators": []},
            "exceptions": {"require_reason": True, "require_expiry": True},
            "enforcement": {"type": "deterministic", "deterministic_checks": ["effective-owner"]},
            "configuration": {"kind": "required-owner", "allowed_values": ["platform"]},
        }
    )

    saved = upsert_policy(pack_path, "AIR-NEW-001", mutation)

    assert "AIR-NEW-001" in _policies(saved)


def test_upsert_policy_rejects_missing_source_section_without_write(tmp_path: Path) -> None:
    pack_path, _ = _write_fixture_pack(tmp_path)
    before = pack_path.read_bytes()
    mutation = _policy_mutation()
    mutation["source_section"] = "No such section"

    with pytest.raises(PolicyEditingError, match="source section"):
        upsert_policy(pack_path, "AIR-DET-001", mutation)

    assert pack_path.read_bytes() == before


def test_upsert_policy_rejects_missing_source_document_without_write(tmp_path: Path) -> None:
    pack_path, _ = _write_fixture_pack(tmp_path)
    before = pack_path.read_bytes()

    with pytest.raises(PolicyEditingError, match="source document not found"):
        upsert_policy(pack_path, "AIR-DET-001", _policy_mutation("standards/missing.md"))

    assert pack_path.read_bytes() == before


def test_upsert_policy_rejects_unreadable_source_without_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pack_path, _ = _write_fixture_pack(tmp_path)
    before = pack_path.read_bytes()
    unreadable = tmp_path / "standards" / "unreadable.md"
    unreadable.write_text("## Ownership and metadata\n", encoding="utf-8")
    mutation = _policy_mutation("standards/unreadable.md")
    real_read_text = Path.read_text

    def read_with_failure(path: Path, *args: Any, **kwargs: Any) -> str:
        if path.resolve() == unreadable.resolve():
            raise OSError("simulated source read failure")
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_with_failure)

    with pytest.raises(OSError, match="simulated source read failure"):
        upsert_policy(pack_path, "AIR-DET-001", mutation)

    assert pack_path.read_bytes() == before


def test_upsert_policy_rejects_conflicting_configuration_vocabulary_without_write(tmp_path: Path) -> None:
    pack_path, _ = _write_fixture_pack(tmp_path)
    before = pack_path.read_bytes()
    mutation: PolicyMutation = {
        **_policy_mutation(),
        "configuration": {"kind": "required-owner", "allowed_values": ["platform"]},
        "check_kind": "required-owner",
        "check_config": {"kind": "required-owner", "allowed_values": ["different"]},
    }

    with pytest.raises(PolicyEditingError, match="configuration vocabulary conflicts"):
        upsert_policy(pack_path, "AIR-DET-001", mutation)

    assert pack_path.read_bytes() == before


def test_upsert_policy_rejects_invalid_whole_pack_without_write(tmp_path: Path) -> None:
    pack_path, _ = _write_fixture_pack(tmp_path)
    before = pack_path.read_bytes()
    mutation: PolicyMutation = {
        **_policy_mutation(),
        "enforcement": {"type": "deterministic", "deterministic_checks": ["time-travel"]},
        "configuration": {"kind": "required-owner", "allowed_values": ["platform"]},
    }

    with pytest.raises(PolicyEditingError, match="unknown deterministic check"):
        upsert_policy(pack_path, "AIR-DET-001", mutation)

    assert pack_path.read_bytes() == before


def test_delete_policy_rejects_gate_reference_without_write(tmp_path: Path) -> None:
    pack_path, _ = _write_fixture_pack(tmp_path)
    _set_gates(pack_path, [{"id": "release", "rules": [{"type": "always-block", "policy_ids": ["AIR-DET-001"]}]}])
    before = pack_path.read_bytes()

    with pytest.raises(PolicyEditingError, match="references unknown policy ids"):
        delete_policy(pack_path, "AIR-DET-001")

    assert pack_path.read_bytes() == before


def test_gate_upsert_replaces_or_appends_without_reordering_other_gates(tmp_path: Path) -> None:
    pack_path, _ = _write_fixture_pack(tmp_path)
    _set_gates(
        pack_path,
        [
            {"id": "release", "rules": [{"type": "no-new-findings"}]},
            {"id": "sandbox", "rules": [{"type": "max-severity", "severity": "low"}]},
        ],
    )

    replaced = upsert_gate(
        pack_path,
        "release",
        {"rules": [{"type": "max-severity", "severity": "critical"}]},
    )
    saved = upsert_gate(
        pack_path,
        "audit",
        {"rules": [{"type": "no-new-findings"}]},
    )

    assert isinstance(replaced, PolicyPack)
    assert [gate.id for gate in saved.quality_gates] == ["release", "sandbox", "audit"]
    assert saved.quality_gates[0].rules[0].model_dump(mode="json") == {
        "type": "max-severity",
        "severity": "critical",
    }


def test_gate_upsert_rejects_mismatched_id_and_unknown_policy(tmp_path: Path) -> None:
    pack_path, _ = _write_fixture_pack(tmp_path)
    _set_gates(pack_path, [{"id": "release", "rules": [{"type": "no-new-findings"}]}])
    before = pack_path.read_bytes()

    with pytest.raises(PolicyEditingError, match="does not match"):
        upsert_gate(
            pack_path,
            "release",
            {"id": "audit", "rules": [{"type": "no-new-findings"}]},
        )
    assert pack_path.read_bytes() == before

    with pytest.raises(PolicyEditingError, match="references unknown policy ids"):
        upsert_gate(
            pack_path,
            "release",
            {"rules": [{"type": "always-block", "policy_ids": ["AIR-NOPE-001"]}]},
        )
    assert pack_path.read_bytes() == before


def test_delete_missing_policy_or_gate_raises_typed_error(tmp_path: Path) -> None:
    pack_path, _ = _write_fixture_pack(tmp_path)

    with pytest.raises(PolicyMemberNotFoundError, match="policy.*not found"):
        delete_policy(pack_path, "AIR-NOPE-001")

    with pytest.raises(PolicyMemberNotFoundError, match="gate.*not found"):
        delete_gate(pack_path, "no-such-gate")
