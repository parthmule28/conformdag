"""Policy source-document resolution and provenance validation."""

from __future__ import annotations

import hashlib
from pathlib import Path

from conformdag.models import PolicyPack


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

        try:
            source_text = source_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            issues.append(f"{policy.id}: cannot read source document {source_path}: {exc}")
            continue
        if policy.source.section not in source_text:
            issues.append(f"{policy.id}: source section {policy.source.section!r} was not found in {source_path}")

        actual_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        if actual_hash.lower() != policy.source.content_hash.lower():
            issues.append(
                f"{policy.id}: source hash mismatch for {source_path} "
                f"(expected {policy.source.content_hash}, got {actual_hash})"
            )
    return issues
