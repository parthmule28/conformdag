"""Typed deterministic evaluator contracts and the initial owner evaluator."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from conformdag.analysis import CallRecord, DagRecord, SourceModel, TaskRecord
from conformdag.models import (
    AirflowProfile,
    EnforcementType,
    ExecutionTimeoutConfig,
    Finding,
    FindingEvidence,
    FindingLocation,
    FindingStatus,
    ForbiddenOperatorsConfig,
    Policy,
    RequiredOwnerConfig,
    RequiredTagsConfig,
    RetryBoundsConfig,
    TopLevelIOConfig,
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


def _finding(
    policy: Policy,
    model: SourceModel,
    line: int,
    status: FindingStatus,
    evidence: str,
    anchor: str,
    remediation: str | None = None,
) -> Finding:
    return Finding(
        policy_id=policy.id,
        policy_version=policy.version,
        status=status,
        severity=policy.severity,
        enforcement=EnforcementType.DETERMINISTIC,
        location=FindingLocation(
            file=Path(model.source.relative_path), start_line=line, end_line=line
        ),
        evidence=FindingEvidence(text=redact_evidence(evidence), start_line=line, end_line=line),
        explanation=evidence,
        remediation=remediation or policy.safe_path,
        fingerprint=structural_fingerprint(policy, model.source.relative_path, anchor, status),
    )


class TagEvaluator:
    policy_id = "AIR-DET-002"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(RequiredTagsConfig, context.policy.configuration)
        findings: list[Finding] = []
        for model in context.models:
            for dag in model.dags:
                tags = {
                    key: value
                    for tag in dag.tags
                    for key, value in [tag.split(":", 1) if ":" in tag else (tag, None)]
                }
                missing = [key for key in configuration.required_keys if key not in tags]
                invalid = [
                    f"{key}={tags[key]!r}"
                    for key, allowed in configuration.allowed_values.items()
                    if key in tags and allowed and tags[key] not in allowed
                ]
                status = FindingStatus.PASS if not missing and not invalid else FindingStatus.FAIL
                detail = (
                    "DAG tags satisfy policy"
                    if status is FindingStatus.PASS
                    else f"missing tags={missing!r}; invalid tags={invalid!r}"
                )
                findings.append(
                    _finding(
                        context.policy,
                        model,
                        dag.line,
                        status,
                        detail,
                        f"dag:{dag.variable_name or dag.line}:tags:{','.join(sorted(dag.tags))}",
                    )
                )
        return findings


def _dag_defaults(model: SourceModel, task: TaskRecord) -> dict[str, object]:
    for dag in model.dags:
        if task.dag_name is None or task.dag_name == dag.variable_name:
            return dag.defaults
    return {}


def _effective_value(model: SourceModel, task: TaskRecord, name: str) -> object:
    if name in task.values:
        return task.values[name]
    return _dag_defaults(model, task).get(name)


class TimeoutEvaluator:
    policy_id = "AIR-DET-003"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(ExecutionTimeoutConfig, context.policy.configuration)
        findings: list[Finding] = []
        for model in context.models:
            for task in model.tasks:
                value = _effective_value(model, task, "execution_timeout")
                if value is None:
                    value = configuration.approved_default_seconds
                seconds = float(value) if isinstance(value, (int, float)) else None
                valid = (
                    seconds is not None
                    and (configuration.min_seconds is None or seconds >= configuration.min_seconds)
                    and (configuration.max_seconds is None or seconds <= configuration.max_seconds)
                )
                status = FindingStatus.PASS if valid else FindingStatus.FAIL
                detail = (
                    f"task {task.task_id or task.qualified_name} "
                    f"effective timeout={value!r} seconds"
                )
                findings.append(
                    _finding(
                        context.policy,
                        model,
                        task.line,
                        status,
                        detail,
                        f"task:{task.task_id or task.line}:timeout:{value!r}",
                    )
                )
        return findings


class RetryEvaluator:
    policy_id = "AIR-DET-004"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(RetryBoundsConfig, context.policy.configuration)
        findings: list[Finding] = []
        for model in context.models:
            for task in model.tasks:
                retries = _effective_value(model, task, "retries")
                delay = _effective_value(model, task, "retry_delay")
                retries = 0 if retries is None else retries
                delay = 0 if delay is None else delay
                valid = (
                    isinstance(retries, (int, float))
                    and configuration.min_retries <= retries <= configuration.max_retries
                    and (configuration.allow_zero_retries or retries > 0)
                    and isinstance(delay, (int, float))
                    and delay >= configuration.min_delay_seconds
                    and (
                        configuration.max_delay_seconds is None
                        or delay <= configuration.max_delay_seconds
                    )
                )
                status = FindingStatus.PASS if valid else FindingStatus.FAIL
                detail = (
                    f"task {task.task_id or task.qualified_name} effective retries={retries!r} "
                    f"retry_delay={delay!r} seconds"
                )
                findings.append(
                    _finding(
                        context.policy,
                        model,
                        task.line,
                        status,
                        detail,
                        f"task:{task.task_id or task.line}:retry:{retries!r}:{delay!r}",
                    )
                )
        return findings


class TopLevelIOEvaluator:
    policy_id = "AIR-DET-005"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(TopLevelIOConfig, context.policy.configuration)
        findings: list[Finding] = []
        for model in context.models:
            for call in model.calls:
                if not call.module_scope:
                    continue
                matched = next(
                    (
                        pattern
                        for pattern in configuration.forbidden_calls
                        if call.qualified_name == pattern
                    ),
                    None,
                )
                if matched:
                    findings.append(
                        _finding(
                            context.policy,
                            model,
                            call.line,
                            FindingStatus.FAIL,
                            f"module-scope call {call.qualified_name} matches forbidden "
                            f"I/O pattern {matched}",
                            f"call:{call.qualified_name}:{call.line}",
                        )
                    )
        return findings


def _resolve_imported_call(model: SourceModel, call: CallRecord) -> str:
    for item in model.imports:
        local_name = item.alias or item.module.rsplit(".", 1)[-1]
        if call.qualified_name == local_name:
            return item.module
        if call.qualified_name.startswith(f"{local_name}.") and item.alias:
            return f"{item.module}{call.qualified_name[len(local_name) :]}"
    return call.qualified_name


class ForbiddenOperatorEvaluator:
    policy_id = "AIR-DET-006"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(ForbiddenOperatorsConfig, context.policy.configuration)
        findings: list[Finding] = []
        for model in context.models:
            for call in model.calls:
                resolved = _resolve_imported_call(model, call)
                if resolved not in configuration.operators:
                    continue
                replacement = configuration.operators[resolved]
                findings.append(
                    _finding(
                        context.policy,
                        model,
                        call.line,
                        FindingStatus.FAIL,
                        f"forbidden operator {resolved}; replacement guidance: {replacement}",
                        f"operator:{resolved}:{call.line}",
                        replacement,
                    )
                )
        return findings


def evaluate_deterministic(
    policies: Iterable[Policy],
    models: Sequence[SourceModel],
    airflow_profile: AirflowProfile | None = None,
) -> tuple[list[Finding], list[str], list[str]]:
    """Evaluate supported deterministic policies with stable policy/file ordering."""
    evaluators: dict[str, DeterministicEvaluator] = {
        "AIR-DET-001": OwnerEvaluator(),
        "AIR-DET-002": TagEvaluator(),
        "AIR-DET-003": TimeoutEvaluator(),
        "AIR-DET-004": RetryEvaluator(),
        "AIR-DET-005": TopLevelIOEvaluator(),
        "AIR-DET-006": ForbiddenOperatorEvaluator(),
    }
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
