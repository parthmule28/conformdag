"""Typed deterministic evaluator contracts and the initial owner evaluator."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from conformdag.analysis import DagRecord, SourceModel
from conformdag.models import (
    AirflowProfile,
    EnforcementType,
    Finding,
    FindingEvidence,
    FindingLocation,
    FindingStatus,
    Policy,
    RequiredOwnerConfig,
)


class EvaluationPhaseError(RuntimeError):
    """Raised when a deterministic evaluator cannot complete its phase."""


@dataclass(frozen=True)
class EvaluationContext:
    policy: Policy
    models: Sequence[SourceModel]
    airflow_profile: AirflowProfile | None = None


class DeterministicEvaluator(Protocol):
    """Common contract implemented by every deterministic policy evaluator."""

    policy_id: str

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        """Evaluate one policy over already-parsed source models."""
        ...


def policy_applies(policy: Policy, airflow_profile: AirflowProfile | None) -> bool:
    """Return whether a policy applies to the selected or source-only profile."""
    return (
        airflow_profile is None
        or not policy.airflow_profiles
        or airflow_profile in policy.airflow_profiles
    )


def redact_evidence(text: str, max_chars: int = 240) -> str:
    """Bound evidence and mask common credential assignments before reporting."""
    bounded = text[:max_chars]
    pattern = re.compile(
        r"(?i)(password|passwd|token|secret|api[_-]?key)\s*=\s*(['\"]?)([^\s,'\"]+)\2"
    )
    return pattern.sub(r"\1=\2[REDACTED]\2", bounded)


def structural_fingerprint(policy: Policy, path: str, anchor: str, status: FindingStatus) -> str:
    """Build a stable finding identity from structural evidence, not line numbers."""
    value = f"{policy.id}:{policy.version}:{path}:{anchor}:{status.value}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class OwnerEvaluator:
    policy_id = "AIR-DET-001"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        if not isinstance(context.policy.configuration, RequiredOwnerConfig):
            raise EvaluationPhaseError("AIR-DET-001 requires a required-owner configuration")
        findings = [
            self._finding(context.policy, model, dag)
            for model in context.models
            for dag in model.dags
        ]
        return sorted(
            findings,
            key=lambda finding: (
                str(finding.location.file),
                finding.location.start_line or 0,
                finding.policy_id,
                finding.status.value,
            ),
        )

    @staticmethod
    def _finding(policy: Policy, model: SourceModel, dag: DagRecord) -> Finding:
        configuration = cast(RequiredOwnerConfig, policy.configuration)
        allowed = bool(dag.owner) and (
            not configuration.allowed_values or dag.owner in configuration.allowed_values
        )
        if configuration.allowed_pattern and dag.owner:
            allowed = allowed and bool(re.fullmatch(configuration.allowed_pattern, dag.owner))
        status = FindingStatus.PASS if allowed else FindingStatus.FAIL
        owner_text = f"effective owner={dag.owner!r} source={dag.owner_source or 'unresolved'}"
        explanation = (
            f"{owner_text} is approved"
            if status is FindingStatus.PASS
            else f"{owner_text} is absent or not approved by policy"
        )
        anchor = f"dag:{dag.variable_name or dag.line}:owner:{dag.owner or 'missing'}"
        return Finding(
            policy_id=policy.id,
            policy_version=policy.version,
            status=status,
            severity=policy.severity,
            enforcement=EnforcementType.DETERMINISTIC,
            location=FindingLocation(
                file=Path(model.source.relative_path),
                start_line=dag.line,
                end_line=dag.line,
            ),
            evidence=FindingEvidence(
                text=redact_evidence(owner_text),
                start_line=dag.line,
                end_line=dag.line,
            ),
            explanation=explanation,
            remediation=policy.safe_path,
            fingerprint=structural_fingerprint(policy, model.source.relative_path, anchor, status),
        )


def evaluate_deterministic(
    policies: Iterable[Policy],
    models: Sequence[SourceModel],
    airflow_profile: AirflowProfile | None = None,
) -> tuple[list[Finding], list[str], list[str]]:
    """Evaluate supported deterministic policies with stable policy/file ordering."""
    evaluators: dict[str, DeterministicEvaluator] = {"AIR-DET-001": OwnerEvaluator()}
    findings: list[Finding] = []
    evaluated: list[str] = []
    skipped: list[str] = []
    for policy in sorted(policies, key=lambda item: item.id):
        if policy.status.value != "ACTIVE" or policy.enforcement.type not in (
            EnforcementType.DETERMINISTIC,
            EnforcementType.HYBRID,
        ):
            skipped.append(policy.id)
            continue
        if not policy_applies(policy, airflow_profile):
            skipped.append(policy.id)
            continue
        evaluator = evaluators.get(policy.id)
        if evaluator is None:
            skipped.append(policy.id)
            continue
        evaluated.append(policy.id)
        findings.extend(evaluator.evaluate(EvaluationContext(policy, models, airflow_profile)))
    return findings, evaluated, skipped
