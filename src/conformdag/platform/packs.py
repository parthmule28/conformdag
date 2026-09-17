"""Policy-pack CRUD: read, validate, and write packs in the working tree."""

from __future__ import annotations

import hashlib
import io
import os
import tempfile
import threading
from contextlib import suppress
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from conformdag.models import Policy, PolicyPack, QualityGate
from conformdag.policy import PolicyValidationError, load_policy_pack, validate_policy_pack


class PackError(ValueError):
    """Raised when a pack cannot be read, written, or validated."""


class PackService:
    """Discovers, reads, validates, and writes policy packs in the workspace."""

    def __init__(self, pack_paths: dict[str, Path] | None = None) -> None:
        self.pack_paths: dict[str, Path] = dict(pack_paths or {})
        self._lock = threading.RLock()

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
                "source_version": policy.source.version,
                "invariant": policy.invariant,
                "safe_path": policy.safe_path,
                "ownership": policy.ownership.model_dump(mode="json"),
                "scope": policy.scope.model_dump(mode="json"),
                "exceptions": policy.exceptions.model_dump(mode="json"),
                "enforcement": policy.enforcement.model_dump(mode="json"),
            }
            for policy in pack.policies
        ]

    def upsert_policy(self, pack_name: str, policy_id: str, policy_data: dict[str, Any]) -> None:
        with self._lock:
            pack_path = self._require_pack(pack_name)
            pack = load_policy_pack(pack_path, pack_path.parent)
            existing = next((policy for policy in pack.policies if policy.id == policy_id), None)
            source_doc = self._resolve_source(pack_path, policy_data["source_document"])
            source_text = source_doc.read_text(encoding="utf-8")
            section = policy_data["source_section"]
            if section not in source_text:
                raise PackError(f"source section {section!r} was not found in {source_doc}")
            content_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()

            clean = _merge_policy_data(policy_id, policy_data, existing, content_hash)
            try:
                validated = Policy.model_validate(clean)
            except ValueError as exc:
                raise PackError(str(exc)) from exc
            idx = next((i for i, p in enumerate(pack.policies) if p.id == policy_id), None)
            if idx is not None:
                pack.policies[idx] = validated
            else:
                pack.policies.append(validated)
            issues = validate_policy_pack(pack)
            if issues:
                raise PackError("; ".join(issues))
            _write_pack(pack, pack_path)

    def delete_policy(self, pack_name: str, policy_id: str) -> None:
        with self._lock:
            pack_path = self._require_pack(pack_name)
            pack = load_policy_pack(pack_path, pack_path.parent)
            before = len(pack.policies)
            pack.policies = [p for p in pack.policies if p.id != policy_id]
            if len(pack.policies) == before:
                raise PackError(f"policy {policy_id} not found in {pack_name}")
            issues = validate_policy_pack(pack)
            if issues:
                raise PackError("; ".join(issues))
            _write_pack(pack, pack_path)

    def list_gates(self, pack_name: str) -> list[dict[str, Any]]:
        pack_path = self._require_pack(pack_name)
        pack = load_policy_pack(pack_path, pack_path.parent)
        return [gate.model_dump(mode="json") for gate in pack.quality_gates]

    def upsert_gate(self, pack_name: str, gate_id: str, gate_data: dict[str, Any]) -> None:
        with self._lock:
            pack_path = self._require_pack(pack_name)
            pack = load_policy_pack(pack_path, pack_path.parent)
            requested_id = gate_data.get("id")
            if requested_id is not None and requested_id != gate_id:
                raise PackError(f"gate id {requested_id!r} does not match requested gate {gate_id!r}")
            clean = dict(gate_data)
            clean["id"] = gate_id
            try:
                gate = QualityGate.model_validate(clean)
            except ValueError as exc:
                raise PackError(str(exc)) from exc
            idx = next((i for i, existing in enumerate(pack.quality_gates) if existing.id == gate_id), None)
            if idx is not None:
                pack.quality_gates[idx] = gate
            else:
                pack.quality_gates.append(gate)
            issues = validate_policy_pack(pack)
            if issues:
                raise PackError("; ".join(issues))
            _write_pack(pack, pack_path)

    def delete_gate(self, pack_name: str, gate_id: str) -> None:
        with self._lock:
            pack_path = self._require_pack(pack_name)
            pack = load_policy_pack(pack_path, pack_path.parent)
            before = len(pack.quality_gates)
            pack.quality_gates = [gate for gate in pack.quality_gates if gate.id != gate_id]
            if len(pack.quality_gates) == before:
                raise PackError(f"gate {gate_id} not found in {pack_name}")
            issues = validate_policy_pack(pack)
            if issues:
                raise PackError("; ".join(issues))
            _write_pack(pack, pack_path)

    def validate_pack(self, pack_name: str) -> dict[str, Any]:
        pack_path = self._require_pack(pack_name)
        try:
            load_policy_pack(pack_path, pack_path.parent)
        except PolicyValidationError as exc:
            return {"valid": False, "errors": str(exc).split("; ")}
        return {"valid": True, "errors": []}

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


def _merge_policy_data(
    policy_id: str,
    policy_data: dict[str, Any],
    existing: Policy | None,
    content_hash: str,
) -> dict[str, Any]:
    """Rebuild one policy payload, preserving contract fields the request omits."""
    if existing is None:
        missing = [key for key in ("ownership", "scope", "exceptions", "enforcement") if policy_data.get(key) is None]
        if missing:
            raise PackError(
                f"new policy {policy_id} requires complete contract metadata; missing: {', '.join(missing)}"
            )
        clean = dict(policy_data)
    else:
        clean = existing.model_dump(mode="json")
    clean.update(
        {
            "id": policy_id,
            "title": policy_data["title"],
            "version": policy_data["version"],
            "status": policy_data["status"],
            "severity": policy_data["severity"],
            "invariant": policy_data["invariant"],
        }
    )
    for key in ("ownership", "scope", "exceptions", "enforcement"):
        if policy_data.get(key) is not None:
            clean[key] = policy_data[key]
    if policy_data.get("safe_path") is not None:
        clean["safe_path"] = policy_data["safe_path"]
    if "check_config" in policy_data or "check_kind" in policy_data:
        configuration = dict(policy_data["check_config"])
        configuration["kind"] = policy_data["check_kind"]
        clean["configuration"] = configuration
    elif "configuration" in policy_data:
        clean["configuration"] = policy_data["configuration"]
    source: dict[str, Any] = {
        "document": policy_data["source_document"],
        "section": policy_data["source_section"],
        "content_hash": content_hash,
    }
    if policy_data.get("source_version") is not None:
        source["version"] = policy_data["source_version"]
    elif existing is not None:
        source["version"] = existing.source.version
    clean["source"] = source
    for key in ("source_document", "source_section", "source_version", "check_kind", "check_config"):
        clean.pop(key, None)
    return clean


def _write_pack(pack: PolicyPack, path: Path) -> None:
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.preserve_quotes = True
    tmp_path: Path | None = None
    try:
        data = pack.model_dump(mode="json")
        buffer = io.StringIO()
        yaml.dump(data, buffer)  # pyright: ignore[reportUnknownMemberType]
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
            mode="w",
            encoding="utf-8",
        ) as handle:
            tmp_path = Path(handle.name)
            handle.write(buffer.getvalue())
        os.replace(tmp_path, path)
    finally:
        if tmp_path is not None:
            with suppress(OSError):
                tmp_path.unlink(missing_ok=True)
