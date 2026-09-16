"""Policy-pack CRUD: read, validate, and write packs in the working tree."""

from __future__ import annotations

import hashlib
import io
import os
from contextlib import suppress
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from conformdag.gates import validate_quality_gates
from conformdag.models import Policy, PolicyPack
from conformdag.policy import PolicyValidationError, load_policy_pack


class PackError(ValueError):
    """Raised when a pack cannot be read, written, or validated."""


class PackService:
    """Discovers, reads, validates, and writes policy packs in the workspace."""

    def __init__(self, pack_paths: dict[str, Path] | None = None) -> None:
        self.pack_paths: dict[str, Path] = dict(pack_paths or {})

    def register(self, name: str, path: Path) -> None:
        self.pack_paths[name] = path

    def list_packs(self) -> list[dict[str, Any]]:
        packs: list[dict[str, Any]] = []
        for name, path in sorted(self.pack_paths.items()):
            entry: dict[str, Any] = {
                "name": name,
                "path": str(path),
                "id": None,
                "version": None,
                "policy_count": 0,
                "error": None,
            }
            try:
                pack = load_policy_pack(path, path.parent)
                entry["id"] = pack.id
                entry["version"] = pack.version
                entry["policy_count"] = len(pack.policies)
            except PolicyValidationError as exc:
                entry["error"] = str(exc)
            packs.append(entry)
        return packs

    def list_policies(self, pack_name: str) -> list[dict[str, Any]]:
        pack_path = self._require_pack(pack_name)
        pack = load_policy_pack(pack_path, pack_path.parent)
        return [
            {
                "id": policy.id,
                "title": policy.title,
                "version": policy.version,
                "status": policy.status.value,
                "severity": policy.severity.value,
                "check_kind": policy.configuration.kind,
                "check_config": policy.configuration.model_dump(mode="json"),
                "source_document": str(policy.source.document),
                "source_section": policy.source.section,
            }
            for policy in pack.policies
        ]

    def upsert_policy(self, pack_name: str, policy_id: str, policy_data: dict[str, Any]) -> None:
        pack_path = self._require_pack(pack_name)
        pack = load_policy_pack(pack_path, pack_path.parent)
        existing = next((policy for policy in pack.policies if policy.id == policy_id), None)
        clean = existing.model_dump(mode="json") if existing is not None else dict(policy_data)
        clean.update(
            {
                "title": policy_data["title"],
                "version": policy_data["version"],
                "status": policy_data["status"],
                "severity": policy_data["severity"],
                "invariant": policy_data["invariant"],
            }
        )
        if policy_data.get("safe_path") is not None:
            clean["safe_path"] = policy_data["safe_path"]
        source_doc = self._resolve_source(pack_path, policy_data.get("source_document", "standards/dag-authoring.md"))
        source_text = source_doc.read_text(encoding="utf-8")
        content_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()

        clean["source"] = {
            "document": policy_data.get("source_document", "standards/dag-authoring.md"),
            "section": policy_data.get("source_section", "Standards"),
            "content_hash": content_hash,
        }
        clean["id"] = policy_id
        if "check_config" in policy_data or "check_kind" in policy_data:
            configuration = dict(policy_data["check_config"])
            configuration["kind"] = policy_data["check_kind"]
            clean["configuration"] = configuration
        elif "configuration" in policy_data:
            clean["configuration"] = policy_data["configuration"]
        for key in ("source_document", "source_section", "check_kind", "check_config"):
            clean.pop(key, None)

        try:
            validated = Policy.model_validate(clean)
        except ValueError as exc:
            raise PackError(str(exc)) from exc
        idx = next((i for i, p in enumerate(pack.policies) if p.id == policy_id), None)
        if idx is not None:
            pack.policies[idx] = validated
        else:
            pack.policies.append(validated)
        _write_pack(pack, pack_path)

    def delete_policy(self, pack_name: str, policy_id: str) -> None:
        pack_path = self._require_pack(pack_name)
        pack = load_policy_pack(pack_path, pack_path.parent)
        before = len(pack.policies)
        pack.policies = [p for p in pack.policies if p.id != policy_id]
        if len(pack.policies) == before:
            raise PackError(f"policy {policy_id} not found in {pack_name}")
        _write_pack(pack, pack_path)

    def validate_pack(self, pack_name: str) -> dict[str, Any]:
        pack_path = self._require_pack(pack_name)
        try:
            pack = load_policy_pack(pack_path, pack_path.parent)
        except PolicyValidationError as exc:
            return {"valid": False, "errors": str(exc).split("; ")}
        issues = validate_quality_gates(pack)
        return {"valid": not issues, "errors": issues}

    def _require_pack(self, pack_name: str) -> Path:
        path = self.pack_paths.get(pack_name)
        if path is None:
            raise PackError(f"pack {pack_name!r} not registered")
        return path

    def _resolve_source(self, pack_path: Path, document: str) -> Path:
        resolved = pack_path.parent / document
        if not resolved.is_file():
            resolved = pack_path.parent.parent / document
        if not resolved.is_file():
            raise PackError(f"source document not found: {document}")
        return resolved


def _write_pack(pack: PolicyPack, path: Path) -> None:
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.preserve_quotes = True
    tmp_path = path.with_name(path.name + ".tmp")
    try:
        data = pack.model_dump(mode="json")
        buffer = io.StringIO()
        yaml.dump(data, buffer)  # pyright: ignore[reportUnknownMemberType]
        tmp_path.write_text(buffer.getvalue(), encoding="utf-8")
        os.replace(tmp_path, path)
    finally:
        with suppress(OSError):
            tmp_path.unlink(missing_ok=True)
