"""Policy-pack CRUD: read, validate, and write packs in the working tree."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from conformdag.models import Policy, QualityGate
from conformdag.policy import PolicyValidationError, load_policy_pack
from conformdag.policy import editing as policy_editing
from conformdag.policy.editing import GateMutation, PolicyEditingError, PolicyMemberNotFoundError, PolicyMutation


class PackError(ValueError):
    """Raised when a pack cannot be read, written, or validated."""


class PackNotFoundError(PackError):
    """Raised when a registered pack or requested pack member does not exist."""


@dataclass(frozen=True)
class PackSummaryData:
    """Internal pack listing metadata, detached from the HTTP response model."""

    name: str
    path: str
    id: str | None
    version: str | None
    policy_count: int
    error: str | None


@dataclass(frozen=True)
class PackValidationResult:
    """Internal result of validating one registered policy pack."""

    valid: bool
    errors: list[str]


class PackService:
    """Discovers, reads, validates, and writes policy packs in the workspace."""

    def __init__(self, pack_paths: dict[str, Path] | None = None) -> None:
        self.pack_paths: dict[str, Path] = dict(pack_paths or {})
        self._lock = threading.RLock()

    def register(self, name: str, path: Path) -> None:
        with self._lock:
            self.pack_paths[name] = path

    def list_packs(self) -> list[PackSummaryData]:
        with self._lock:
            packs: list[PackSummaryData] = []
            for name, path in sorted(self.pack_paths.items()):
                pack_id: str | None = None
                version: str | None = None
                policy_count = 0
                error: str | None = None
                try:
                    pack = load_policy_pack(path, path.parent)
                    pack_id = pack.id
                    version = pack.version
                    policy_count = len(pack.policies)
                except PolicyValidationError as exc:
                    error = str(exc)
                packs.append(
                    PackSummaryData(
                        name=name,
                        path=str(path),
                        id=pack_id,
                        version=version,
                        policy_count=policy_count,
                        error=error,
                    )
                )
            return packs

    def list_policies(self, pack_name: str) -> list[Policy]:
        with self._lock:
            pack_path = self._require_pack(pack_name)
            pack = load_policy_pack(pack_path, pack_path.parent)
            return list(pack.policies)

    def upsert_policy(self, pack_name: str, policy_id: str, mutation: PolicyMutation) -> None:
        with self._lock:
            pack_path = self._require_pack(pack_name)
            try:
                policy_editing.upsert_policy(pack_path, policy_id, mutation)
            except PolicyMemberNotFoundError as exc:
                raise PackNotFoundError(str(exc)) from exc
            except PolicyEditingError as exc:
                raise PackError(str(exc)) from exc

    def delete_policy(self, pack_name: str, policy_id: str) -> None:
        with self._lock:
            pack_path = self._require_pack(pack_name)
            try:
                policy_editing.delete_policy(pack_path, policy_id)
            except PolicyMemberNotFoundError as exc:
                raise PackNotFoundError(f"policy {policy_id} not found in {pack_name}") from exc
            except PolicyEditingError as exc:
                raise PackError(str(exc)) from exc

    def list_gates(self, pack_name: str) -> list[QualityGate]:
        with self._lock:
            pack_path = self._require_pack(pack_name)
            pack = load_policy_pack(pack_path, pack_path.parent)
            return list(pack.quality_gates)

    def upsert_gate(self, pack_name: str, gate_id: str, mutation: GateMutation) -> None:
        with self._lock:
            pack_path = self._require_pack(pack_name)
            try:
                policy_editing.upsert_gate(pack_path, gate_id, mutation)
            except PolicyMemberNotFoundError as exc:
                raise PackNotFoundError(str(exc)) from exc
            except PolicyEditingError as exc:
                raise PackError(str(exc)) from exc

    def delete_gate(self, pack_name: str, gate_id: str) -> None:
        with self._lock:
            pack_path = self._require_pack(pack_name)
            try:
                policy_editing.delete_gate(pack_path, gate_id)
            except PolicyMemberNotFoundError as exc:
                raise PackNotFoundError(f"gate {gate_id} not found in {pack_name}") from exc
            except PolicyEditingError as exc:
                raise PackError(str(exc)) from exc

    def validate_pack(self, pack_name: str) -> PackValidationResult:
        with self._lock:
            pack_path = self._require_pack(pack_name)
            try:
                load_policy_pack(pack_path, pack_path.parent)
            except PolicyValidationError as exc:
                return PackValidationResult(valid=False, errors=str(exc).split("; "))
            return PackValidationResult(valid=True, errors=[])

    def _require_pack(self, pack_name: str) -> Path:
        path = self.pack_paths.get(pack_name)
        if path is None:
            raise PackNotFoundError(f"pack {pack_name!r} not registered")
        return path
