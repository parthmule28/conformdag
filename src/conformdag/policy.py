"""Policy-pack loading, validation, provenance, and suppression helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from ruamel.yaml import YAML

from conformdag.models import LifecycleStatus, Policy, PolicyPack, Suppression


class PolicyValidationError(ValueError):
    """Raised when a policy pack or its provenance is invalid."""

    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))


def _yaml() -> YAML:
    yaml = YAML(typ="safe")
    yaml.default_flow_style = False
    return yaml


def _read_yaml(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as stream:
            return _yaml().load(stream)  # pyright: ignore[reportUnknownMemberType]
    except OSError as exc:
        raise PolicyValidationError([f"cannot read {path}: {exc}"]) from exc
    except Exception as exc:
        raise PolicyValidationError([f"invalid YAML in {path}: {exc}"]) from exc


def resolve_policy_pack_path(path: Path, *, working_directory: Path | None = None) -> Path:
    """Resolve a relative policy pack path from the invoker's working directory."""
    if path.is_absolute():
        return path.resolve()
    base = (working_directory or Path.cwd()).resolve()
    return (base / path).resolve()


def resolve_configured_policy_pack(
    configured: Path,
    *,
    scan_root: Path,
    from_cli: bool,
    working_directory: Path | None = None,
) -> Path:
    """Resolve a policy pack from CLI options or project configuration."""
    if configured.is_absolute():
        return configured.resolve()
    if from_cli:
        return resolve_policy_pack_path(configured, working_directory=working_directory)
    return (scan_root / configured).resolve()


def resolve_source_document(
    document: Path,
    *,
    pack_path: Path,
    repository_root: Path,
) -> Path:
    """Locate a policy source document relative to the pack or scanned repository."""
    if document.is_absolute():
        return document.resolve()
    pack_path = pack_path.resolve()
    repository_root = repository_root.resolve()
    for candidate in (
        pack_path.parent / document,
        pack_path.parent.parent / document,
        repository_root / document,
    ):
        if candidate.is_file():
            return candidate.resolve()
    return (repository_root / document).resolve()


def load_policy_pack(path: Path, repository_root: Path | None = None) -> PolicyPack:
    """Load and validate one policy pack, including local source provenance."""
    raw: Any = _read_yaml(path)
    if not isinstance(raw, dict):
        raise PolicyValidationError([f"policy pack {path} must contain a YAML mapping"])

    try:
        pack = PolicyPack.model_validate(raw)
    except ValueError as exc:
        raise PolicyValidationError([str(exc)]) from exc

    pack_path = path.resolve()
    root = (repository_root or pack_path.parent).resolve()
    issues = validate_policy_provenance(pack, pack_path=pack_path, repository_root=root)
    if issues:
        raise PolicyValidationError(issues)
    return pack


def select_policy_pack(path: Path | None, repository_root: Path) -> PolicyPack:
    """Load one explicit pack, or reject implicit composition of multiple packs."""
    if path is not None:
        return load_policy_pack(path.resolve(), repository_root)
    candidates = sorted(
        candidate
        for pattern in ("*.yaml", "*.yml")
        for candidate in (repository_root / "policies").glob(pattern)
    )
    if len(candidates) != 1:
        raise PolicyValidationError(
            [
                "exactly one policy pack must be selected; "
                f"found {len(candidates)} candidates under {repository_root / 'policies'}"
            ]
        )
    return load_policy_pack(candidates[0], repository_root)


def validate_policy_provenance(
    pack: PolicyPack,
    *,
    pack_path: Path,
    repository_root: Path,
) -> list[str]:
    """Return all missing, malformed, or changed local source references."""
    issues: list[str] = []
    for policy in pack.policies:
        source_path = resolve_source_document(
            policy.source.document,
            pack_path=pack_path,
            repository_root=repository_root,
        )
        if not source_path.is_file():
            issues.append(f"{policy.id}: source document does not exist: {source_path}")
            continue

        source_text = source_path.read_text(encoding="utf-8")
        if policy.source.section not in source_text:
            issues.append(
                f"{policy.id}: source section {policy.source.section!r} was not found "
                f"in {source_path}"
            )

        actual_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        if actual_hash.lower() != policy.source.content_hash.lower():
            issues.append(
                f"{policy.id}: source hash mismatch for {source_path} "
                f"(expected {policy.source.content_hash}, got {actual_hash})"
            )
    return issues


def active_policies(pack: PolicyPack) -> list[Policy]:
    """Return only policies that are eligible for evaluation."""
    return [policy for policy in pack.policies if policy.status is LifecycleStatus.ACTIVE]


def _policy_hash(payload: object) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def policy_contract_hash(policy: Policy) -> str:
    """Hash the policy contract independently from its enforcement machinery."""
    return _policy_hash(
        {
            "id": policy.id,
            "title": policy.title,
            "severity": policy.severity.value,
            "scope": policy.scope.model_dump(mode="json"),
            "invariant": policy.invariant,
            "safe_path": policy.safe_path,
            "exceptions": policy.exceptions.model_dump(mode="json"),
            "configuration": policy.configuration.model_dump(mode="json"),
        }
    )


def policy_enforcement_hash(policy: Policy) -> str:
    """Hash the enforcement contract used to execute or prompt a policy."""
    return _policy_hash(policy.enforcement.model_dump(mode="json"))


def load_suppressions(path: Path) -> list[Suppression]:
    """Load a suppression list from a YAML sequence or ``suppressions`` mapping."""
    if not path.exists():
        return []
    raw: Any = _read_yaml(path)
    if raw is None:
        return []
    if isinstance(raw, dict):
        raw = cast(dict[str, Any], raw).get("suppressions", [])
    if not isinstance(raw, list):
        raise PolicyValidationError([f"suppression file {path} must contain a YAML sequence"])
    items = cast(list[Any], raw)
    try:
        return [Suppression.model_validate(item) for item in items]
    except ValueError as exc:
        raise PolicyValidationError([str(exc)]) from exc
