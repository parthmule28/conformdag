"""Canonical policy-pack editing operations."""

from __future__ import annotations

import hashlib
import io
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any, NotRequired, Required, TypedDict, cast

from pydantic import TypeAdapter
from ruamel.yaml import YAML

from conformdag.models import GateRule, Policy, PolicyConfiguration, PolicyPack, QualityGate
from conformdag.policy.loading import load_policy_pack
from conformdag.policy.provenance import resolve_source_document, validate_policy_provenance
from conformdag.policy.validation import validate_policy_pack


class PolicyMutation(TypedDict, total=False):
    """Typed editable policy fields accepted independently of any transport DTO."""

    title: Required[str]
    version: Required[str]
    status: Required[str]
    severity: Required[str]
    source_document: Required[str]
    source_section: Required[str]
    invariant: Required[str]
    id: NotRequired[str | None]
    airflow_profiles: NotRequired[list[str] | None]
    source_version: NotRequired[str | None]
    ownership: NotRequired[dict[str, object] | None]
    scope: NotRequired[dict[str, object] | None]
    exceptions: NotRequired[dict[str, object] | None]
    enforcement: NotRequired[dict[str, object] | None]
    safe_path: NotRequired[str | None]
    tags: NotRequired[list[str] | None]
    deterministic_checks: NotRequired[list[str] | None]
    configuration: NotRequired[dict[str, object] | None]
    check_kind: NotRequired[str | None]
    check_config: NotRequired[dict[str, object] | None]


class GateMutation(TypedDict, total=False):
    """Typed editable quality-gate fields independent of any transport DTO."""

    rules: Required[list[GateRule | dict[str, object]]]
    id: NotRequired[str | None]


class PolicyEditingError(ValueError):
    """Raised when a requested policy or gate edit would produce an invalid pack."""


class PolicyMemberNotFoundError(PolicyEditingError):
    """Raised when an edit requests deletion of a policy or gate that is absent."""


_POLICY_CONFIGURATION_ADAPTER: TypeAdapter[PolicyConfiguration] = TypeAdapter(PolicyConfiguration)


def upsert_policy(pack_path: Path, policy_id: str, mutation: PolicyMutation) -> PolicyPack:
    """Create or update one policy, refreshing its source provenance before an atomic write."""
    pack = load_policy_pack(pack_path, pack_path.parent)
    existing = next((policy for policy in pack.policies if policy.id == policy_id), None)
    policy_data: dict[str, Any] = {key: value for key, value in mutation.items() if value is not None}

    source_doc = resolve_source_document(
        Path(policy_data["source_document"]),
        pack_path=pack_path,
        repository_root=pack_path.parent,
    )
    if not source_doc.is_file():
        raise PolicyEditingError(f"source document not found: {policy_data['source_document']}")
    source_text = source_doc.read_text(encoding="utf-8")
    section = policy_data["source_section"]
    if section not in source_text:
        raise PolicyEditingError(f"source section {section!r} was not found in {source_doc}")
    content_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()

    clean = _merge_policy_data(policy_id, policy_data, existing, content_hash)
    try:
        validated = Policy.model_validate(clean)
    except ValueError as exc:
        raise PolicyEditingError(str(exc)) from exc

    index = next((index for index, policy in enumerate(pack.policies) if policy.id == policy_id), None)
    if index is None:
        pack.policies.append(validated)
    else:
        pack.policies[index] = validated

    return _validate_and_write(pack, pack_path)


def delete_policy(pack_path: Path, policy_id: str) -> PolicyPack:
    """Remove one policy if the remaining pack, including its gates, remains valid."""
    pack = load_policy_pack(pack_path, pack_path.parent)
    before = len(pack.policies)
    pack.policies = [policy for policy in pack.policies if policy.id != policy_id]
    if len(pack.policies) == before:
        raise PolicyMemberNotFoundError(f"policy {policy_id} not found in {pack_path}")
    return _validate_and_write(pack, pack_path)


def upsert_gate(pack_path: Path, gate_id: str, mutation: GateMutation) -> PolicyPack:
    """Create or replace one quality gate, then validate the complete pack."""
    pack = load_policy_pack(pack_path, pack_path.parent)
    requested_id = mutation.get("id")
    if requested_id is not None and requested_id != gate_id:
        raise PolicyEditingError(f"gate id {requested_id!r} does not match requested gate {gate_id!r}")
    clean: dict[str, Any] = dict(mutation)
    clean["id"] = gate_id
    try:
        gate = QualityGate.model_validate(clean)
    except ValueError as exc:
        raise PolicyEditingError(str(exc)) from exc

    index = next((index for index, existing in enumerate(pack.quality_gates) if existing.id == gate_id), None)
    if index is None:
        pack.quality_gates.append(gate)
    else:
        pack.quality_gates[index] = gate
    return _validate_and_write(pack, pack_path)


def delete_gate(pack_path: Path, gate_id: str) -> PolicyPack:
    """Remove one gate from a valid pack."""
    pack = load_policy_pack(pack_path, pack_path.parent)
    before = len(pack.quality_gates)
    pack.quality_gates = [gate for gate in pack.quality_gates if gate.id != gate_id]
    if len(pack.quality_gates) == before:
        raise PolicyMemberNotFoundError(f"gate {gate_id} not found in {pack_path}")
    return _validate_and_write(pack, pack_path)


def _validate_and_write(pack: PolicyPack, pack_path: Path) -> PolicyPack:
    """Validate all policy provenance and pack semantics before replacing the source file."""
    issues = validate_policy_provenance(pack, pack_path=pack_path, repository_root=pack_path.parent)
    issues.extend(validate_policy_pack(pack))
    if issues:
        raise PolicyEditingError("; ".join(issues))
    _write_pack(pack, pack_path)
    return pack


def _merge_policy_data(
    policy_id: str,
    policy_data: dict[str, Any],
    existing: Policy | None,
    content_hash: str,
) -> dict[str, Any]:
    """Rebuild one policy payload, preserving contract fields the mutation omits."""
    if existing is None:
        missing = [key for key in ("ownership", "scope", "exceptions", "enforcement") if policy_data.get(key) is None]
        if missing:
            raise PolicyEditingError(
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
    if policy_data.get("tags") is not None:
        clean["tags"] = policy_data["tags"]
    elif existing is None:
        clean.pop("tags", None)
    _merge_configuration_vocabulary(clean, policy_data)
    _merge_deterministic_vocabulary(clean, policy_data, existing)
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
    for key in (
        "source_document",
        "source_section",
        "source_version",
        "deterministic_checks",
        "check_kind",
        "check_config",
    ):
        clean.pop(key, None)
    return clean


def _normalize_configuration(value: object) -> dict[str, Any]:
    """Validate and serialize one typed policy configuration for comparison."""
    try:
        configuration: PolicyConfiguration = _POLICY_CONFIGURATION_ADAPTER.validate_python(value)
    except ValueError as exc:
        raise PolicyEditingError(f"invalid policy configuration: {exc}") from exc
    return configuration.model_dump(mode="json")


def _merge_configuration_vocabulary(clean: dict[str, Any], policy_data: dict[str, Any]) -> None:
    """Resolve canonical and beta configuration names without silent precedence."""
    has_configuration = "configuration" in policy_data
    has_check_kind = "check_kind" in policy_data
    has_check_config = "check_config" in policy_data
    if has_check_kind != has_check_config:
        raise PolicyEditingError("check_kind and check_config must be supplied together")

    canonical: dict[str, Any] | None = None
    if has_configuration:
        canonical = _normalize_configuration(policy_data["configuration"])

    if has_check_kind:
        check_kind = policy_data["check_kind"]
        check_config = policy_data["check_config"]
        if not isinstance(check_kind, str) or not isinstance(check_config, dict):
            raise PolicyEditingError("legacy check_kind and check_config must have valid types")
        legacy_config = cast("dict[str, Any]", check_config)
        legacy: dict[str, Any] = dict(legacy_config)
        embedded_kind: object = legacy.get("kind")
        if embedded_kind is not None and embedded_kind != check_kind:
            raise PolicyEditingError("configuration vocabulary conflicts: check_kind does not match check_config.kind")
        legacy["kind"] = check_kind
        legacy_normalized = _normalize_configuration(legacy)
        if canonical is not None and canonical != legacy_normalized:
            raise PolicyEditingError("configuration vocabulary conflicts between configuration and legacy fields")
        canonical = legacy_normalized

    if canonical is not None:
        clean["configuration"] = canonical


def _merge_deterministic_vocabulary(
    clean: dict[str, Any], policy_data: dict[str, Any], existing: Policy | None
) -> None:
    """Resolve the additive check list against the nested enforcement projection."""
    has_checks = "deterministic_checks" in policy_data
    has_enforcement = "enforcement" in policy_data
    if not has_checks:
        return

    raw_checks = policy_data["deterministic_checks"]
    if not isinstance(raw_checks, list):
        raise PolicyEditingError("deterministic_checks must be a list of strings")
    checks_as_objects = cast("list[object]", raw_checks)
    if not all(isinstance(check, str) for check in checks_as_objects):
        raise PolicyEditingError("deterministic_checks must be a list of strings")
    checks = cast("list[str]", raw_checks)

    if has_enforcement:
        raw_enforcement = clean.get("enforcement")
        if not isinstance(raw_enforcement, dict):
            raise PolicyEditingError("enforcement must be an object")
        enforcement = dict(cast("dict[str, Any]", raw_enforcement))
        clean["enforcement"] = enforcement
        nested_checks = enforcement.get("deterministic_checks")
        if nested_checks is not None and nested_checks != checks:
            raise PolicyEditingError("deterministic check vocabulary conflicts with enforcement.deterministic_checks")
        enforcement["deterministic_checks"] = list(checks)
        return

    if existing is not None:
        raw_enforcement = clean.get("enforcement")
        if not isinstance(raw_enforcement, dict):
            raise PolicyEditingError("existing policy enforcement must be an object")
        enforcement = dict(cast("dict[str, Any]", raw_enforcement))
        clean["enforcement"] = enforcement
        enforcement["deterministic_checks"] = list(checks)


def _write_pack(pack: PolicyPack, path: Path) -> None:
    """Atomically serialize a validated pack using a temporary file beside its destination."""
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
