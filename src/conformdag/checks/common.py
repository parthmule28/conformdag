"""Shared contracts and finding helpers for deterministic checks."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from conformdag.analysis import SourceModel
from conformdag.models import (
    AirflowProfile,
    EnforcementType,
    Finding,
    FindingEvidence,
    FindingLocation,
    FindingStatus,
    Policy,
    RemediationPayload,
    RemediationTarget,
)


class EvaluationPhaseError(RuntimeError):
    """Raised when a deterministic evaluator cannot complete its phase."""


def fix_target(
    line: int,
    enclosing: str | None,
    node: Literal["dag-call", "task-call", "statement"],
) -> RemediationTarget:
    return RemediationTarget(line=line, enclosing=enclosing, node=node)


@dataclass(frozen=True)
class EvaluationContext:
    policy: Policy
    models: Sequence[SourceModel]
    airflow_profile: AirflowProfile | None = None
    repository_root: Path | None = None
    ruff_violations: list[dict[str, Any]] | None = None


class DeterministicEvaluator(Protocol):
    """Common contract implemented by every deterministic policy evaluator."""

    policy_id: str

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        """Evaluate one policy over already-parsed source models."""
        ...


def policy_applies(policy: Policy, airflow_profile: AirflowProfile | None) -> bool:
    """Return whether a policy applies to the selected or source-only profile."""
    return airflow_profile is None or not policy.airflow_profiles or airflow_profile in policy.airflow_profiles


def redact_evidence(text: str, max_chars: int = 240) -> str:
    """Bound evidence and mask common credential assignments before reporting."""
    bounded = text[:max_chars]
    pattern = re.compile(r"(?i)(password|passwd|token|secret|api[_-]?key)\s*=\s*(['\"]?)([^\s,'\"]+)\2")
    return pattern.sub(r"\1=\2[REDACTED]\2", bounded)


def structural_fingerprint(policy: Policy, path: str, anchor: str, status: FindingStatus) -> str:
    """Build a stable finding identity from structural evidence, not line numbers."""
    value = f"{policy.id}:{policy.version}:{path}:{anchor}:{status.value}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def finding(
    policy: Policy,
    model: SourceModel,
    line: int,
    status: FindingStatus,
    evidence: str,
    anchor: str,
    remediation: str | None = None,
    fix_payload: RemediationPayload | None = None,
) -> Finding:
    return Finding(
        policy_id=policy.id,
        policy_version=policy.version,
        status=status,
        severity=policy.severity,
        enforcement=EnforcementType.DETERMINISTIC,
        location=FindingLocation(file=Path(model.source.relative_path), start_line=line, end_line=line),
        evidence=FindingEvidence(text=redact_evidence(evidence), start_line=line, end_line=line),
        explanation=evidence,
        remediation=remediation or policy.safe_path,
        fix=fix_payload,
        fingerprint=structural_fingerprint(policy, model.source.relative_path, anchor, status),
    )


_finding = finding
