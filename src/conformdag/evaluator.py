"""Typed deterministic evaluator contracts and the initial owner evaluator."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from conformdag.analysis import (
    CallRecord,
    DagRecord,
    SourceModel,
    TaskRecord,
    secret_like,
)
from conformdag.models import (
    AirflowProfile,
    CatchupPolicyConfig,
    DynamicDagFactoryConfig,
    EnforcementType,
    ExecutionTimeoutConfig,
    Finding,
    FindingEvidence,
    FindingLocation,
    FindingStatus,
    ForbiddenOperatorsConfig,
    ModuleScopeVariablesConfig,
    OperatorRule,
    Policy,
    RemediationAction,
    RemediationPayload,
    RemediationTarget,
    RequiredOwnerConfig,
    RequiredTagsConfig,
    RetryBoundsConfig,
    RuffAirConfig,
    SensitiveLoggingConfig,
    StartDateFreshnessConfig,
    TopLevelIOConfig,
)
from conformdag.ruff_adapter import run_ruff


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


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split(".") if part.isdigit())


class OwnerEvaluator:
    policy_id = "AIR-DET-001"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        if not isinstance(context.policy.configuration, RequiredOwnerConfig):
            raise EvaluationPhaseError("AIR-DET-001 requires a required-owner configuration")
        findings = [self._finding(context.policy, model, dag) for model in context.models for dag in model.dags]
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
        allowed = bool(dag.owner) and (not configuration.allowed_values or dag.owner in configuration.allowed_values)
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
        payload: RemediationPayload | None = None
        if status is FindingStatus.FAIL:
            enclosing = dag.variable_name or f"dag@{dag.line}"
            if configuration.allowed_values:
                value = sorted(configuration.allowed_values)[0]
                action = RemediationAction.SET_KWARG if dag.owner else RemediationAction.ADD_OWNER
                payload = RemediationPayload(
                    fix_kind="required-owner",
                    action=action,
                    kwarg="owner",
                    target=fix_target(dag.line, enclosing, "dag-call"),
                    value=value,
                    hint=f'sets owner="{value}" on the DAG call',
                )
            elif configuration.allowed_pattern:
                payload = RemediationPayload(
                    fix_kind="required-owner",
                    action=RemediationAction.MANUAL,
                    target=fix_target(dag.line, enclosing, "dag-call"),
                    hint="policy constrains owner by pattern; choose a compliant owner value",
                )
            else:
                payload = RemediationPayload(
                    fix_kind="required-owner",
                    action=RemediationAction.MANUAL,
                    target=fix_target(dag.line, enclosing, "dag-call"),
                    hint="policy declares no allowed values; configure allowed_values or allowed_pattern",
                )
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
            fix=payload,
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


class TagEvaluator:
    policy_id = "AIR-DET-002"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(RequiredTagsConfig, context.policy.configuration)
        findings: list[Finding] = []
        for model in context.models:
            for dag in model.dags:
                tags = {
                    key: value for tag in dag.tags for key, value in [tag.split(":", 1) if ":" in tag else (tag, None)]
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
                payload: RemediationPayload | None = None
                if status is FindingStatus.FAIL:
                    enclosing = dag.variable_name or f"dag@{dag.line}"
                    if invalid:
                        payload = RemediationPayload(
                            fix_kind="required-tags",
                            action=RemediationAction.MANUAL,
                            target=fix_target(dag.line, enclosing, "dag-call"),
                            hint="tags carry disallowed values; choose compliant values from policy",
                        )
                    elif missing:
                        additions = [
                            f"{key}:{sorted(configuration.allowed_values[key])[0]}"
                            if configuration.allowed_values.get(key)
                            else key
                            for key in missing
                        ]
                        payload = RemediationPayload(
                            fix_kind="required-tags",
                            action=RemediationAction.ADD_TAGS,
                            kwarg="tags",
                            target=fix_target(dag.line, enclosing, "dag-call"),
                            value=json.dumps(additions),
                            hint=f"adds compliant tags {additions!r} to the DAG tags list",
                        )
                findings.append(
                    _finding(
                        context.policy,
                        model,
                        dag.line,
                        status,
                        detail,
                        f"dag:{dag.variable_name or dag.line}:tags:{','.join(sorted(dag.tags))}",
                        fix_payload=payload,
                    )
                )
        return findings


def _dag_defaults(model: SourceModel, task: TaskRecord) -> dict[str, object]:
    if task.dag_line is not None:
        for dag in model.dags:
            if dag.line == task.dag_line:
                return dag.defaults
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
                detail = f"task {task.task_id or task.qualified_name} effective timeout={value!r} seconds"
                payload: RemediationPayload | None = None
                if status is FindingStatus.FAIL:
                    target_seconds = self._target_seconds(configuration, seconds)
                    if target_seconds is None:
                        payload = RemediationPayload(
                            fix_kind="execution-timeout",
                            action=RemediationAction.MANUAL,
                            target=fix_target(task.line, task.task_id or task.qualified_name, "task-call"),
                            hint="policy sets no approved default or bounds; configure approved_default_seconds",
                        )
                    else:
                        present = "execution_timeout" in task.values
                        payload = RemediationPayload(
                            fix_kind="execution-timeout",
                            action=RemediationAction.SET_KWARG if present else RemediationAction.ADD_KWARG,
                            kwarg="execution_timeout",
                            target=fix_target(task.line, task.task_id or task.qualified_name, "task-call"),
                            value=str(int(target_seconds)),
                            hint=f"sets execution_timeout=timedelta(seconds={int(target_seconds)}) on the task",
                        )
                findings.append(
                    _finding(
                        context.policy,
                        model,
                        task.line,
                        status,
                        detail,
                        f"task:{task.task_id or task.line}:timeout:{value!r}",
                        fix_payload=payload,
                    )
                )
        return findings

    @staticmethod
    def _target_seconds(configuration: ExecutionTimeoutConfig, seconds: float | None) -> int | None:
        if seconds is None:
            if configuration.approved_default_seconds is not None:
                return configuration.approved_default_seconds
            if configuration.max_seconds is not None:
                return configuration.max_seconds
            if configuration.min_seconds is not None:
                return configuration.min_seconds
            return None
        if configuration.min_seconds is not None and seconds < configuration.min_seconds:
            return configuration.min_seconds
        if configuration.max_seconds is not None and seconds > configuration.max_seconds:
            return configuration.max_seconds
        return None


class RetryEvaluator:
    policy_id = "AIR-DET-004"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(RetryBoundsConfig, context.policy.configuration)
        findings: list[Finding] = []
        for model in context.models:
            for task in model.tasks:
                unresolved = sorted(name for name in ("retries", "retry_delay") if name in task.unresolved_kwargs)
                if unresolved:
                    findings.append(self._unresolved_finding(context, model, task, unresolved))
                    continue
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
                    and (configuration.max_delay_seconds is None or delay <= configuration.max_delay_seconds)
                )
                status = FindingStatus.PASS if valid else FindingStatus.FAIL
                detail = (
                    f"task {task.task_id or task.qualified_name} effective retries={retries!r} "
                    f"retry_delay={delay!r} seconds"
                )
                payload: RemediationPayload | None = None
                if status is FindingStatus.FAIL:
                    payload = self._payload(configuration, task, retries, delay)
                findings.append(
                    _finding(
                        context.policy,
                        model,
                        task.line,
                        status,
                        detail,
                        f"task:{task.task_id or task.line}:retry:{retries!r}:{delay!r}",
                        fix_payload=payload,
                    )
                )
        return findings

    @staticmethod
    def _unresolved_finding(
        context: EvaluationContext,
        model: SourceModel,
        task: TaskRecord,
        unresolved: list[str],
    ) -> Finding:
        task_label = task.task_id or task.qualified_name
        names = ", ".join(unresolved)
        return _finding(
            context.policy,
            model,
            task.line,
            FindingStatus.ERROR,
            f"task {task_label} sets dynamic {names}; the effective value cannot be verified statically",
            f"task:{task_label}:retry:unresolved:{'+'.join(unresolved)}",
            fix_payload=RemediationPayload(
                fix_kind="retry-bounds",
                action=RemediationAction.MANUAL,
                target=fix_target(task.line, task_label, "task-call"),
                hint="replace the dynamic value with numeric literals within policy bounds",
            ),
        )

    @staticmethod
    def _payload(
        configuration: RetryBoundsConfig,
        task: TaskRecord,
        retries: object,
        delay: object,
    ) -> RemediationPayload:
        enclosing = task.task_id or task.qualified_name
        if not isinstance(retries, (int, float)) or not isinstance(delay, (int, float)):
            return RemediationPayload(
                fix_kind="retry-bounds",
                action=RemediationAction.MANUAL,
                target=fix_target(task.line, enclosing, "task-call"),
                hint="retries or retry_delay is not a numeric literal; set them manually",
            )
        new_retries = int(retries)
        if new_retries < configuration.min_retries:
            new_retries = configuration.min_retries
        elif new_retries > configuration.max_retries:
            new_retries = configuration.max_retries
        elif new_retries == 0 and not configuration.allow_zero_retries:
            new_retries = max(configuration.min_retries, 1)
        new_delay: int | None = None
        if delay < configuration.min_delay_seconds:
            new_delay = configuration.min_delay_seconds
        elif configuration.max_delay_seconds is not None and delay > configuration.max_delay_seconds:
            new_delay = configuration.max_delay_seconds
        retries_changed = new_retries != int(retries)
        if retries_changed:
            hint = f"sets retries={new_retries} on the task"
            if new_delay is not None:
                hint += f" and retry_delay=timedelta(seconds={new_delay})"
            return RemediationPayload(
                fix_kind="retry-bounds",
                action=(RemediationAction.SET_KWARG if "retries" in task.values else RemediationAction.ADD_KWARG),
                kwarg="retries",
                target=fix_target(task.line, enclosing, "task-call"),
                value=str(new_retries),
                hint=hint,
            )
        if new_delay is not None:
            present = "retry_delay" in task.values
            return RemediationPayload(
                fix_kind="retry-bounds",
                action=RemediationAction.SET_KWARG if present else RemediationAction.ADD_KWARG,
                kwarg="retry_delay",
                target=fix_target(task.line, enclosing, "task-call"),
                value=str(new_delay),
                hint=f"sets retry_delay=timedelta(seconds={new_delay}) on the task",
            )
        return RemediationPayload(
            fix_kind="retry-bounds",
            action=RemediationAction.MANUAL,
            target=fix_target(task.line, enclosing, "task-call"),
            hint="retry values could not be clamped into policy bounds automatically",
        )


class TopLevelIOEvaluator:
    policy_id = "AIR-DET-005"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(TopLevelIOConfig, context.policy.configuration)
        findings: list[Finding] = []
        for model in context.models:
            for call in model.calls:
                if not call.module_scope:
                    continue
                if call.uncertain and configuration.uncertain_as_review:
                    findings.append(
                        _finding(
                            context.policy,
                            model,
                            call.line,
                            FindingStatus.NEEDS_REVIEW,
                            "module-scope dynamic call could not be classified with high confidence",
                            f"dynamic-call:{call.line}:{call.column}",
                            fix_payload=RemediationPayload(
                                fix_kind="top-level-io",
                                action=RemediationAction.MANUAL,
                                target=fix_target(call.line, None, "statement"),
                                hint="dynamic module-scope call needs human review",
                            ),
                        )
                    )
                    continue
                matched = next(
                    (pattern for pattern in configuration.forbidden_calls if call.qualified_name == pattern),
                    None,
                )
                if matched:
                    findings.append(
                        _finding(
                            context.policy,
                            model,
                            call.line,
                            FindingStatus.FAIL,
                            f"module-scope call {call.qualified_name} matches forbidden I/O pattern {matched}",
                            f"call:{call.qualified_name}:{call.line}",
                            fix_payload=RemediationPayload(
                                fix_kind="top-level-io",
                                action=RemediationAction.MOVE_STATEMENT,
                                target=fix_target(call.line, call.qualified_name, "statement"),
                                hint="proposed-only structural move of the module-scope "
                                "statement into a task callable; never auto-applied",
                            ),
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
                rule = configuration.operators[resolved]
                if isinstance(rule, OperatorRule):
                    if (
                        context.airflow_profile is not None
                        and rule.airflow_profiles
                        and context.airflow_profile not in rule.airflow_profiles
                    ):
                        continue
                    profile_version = (
                        _version_tuple(context.airflow_profile.value) if context.airflow_profile is not None else None
                    )
                    if (
                        profile_version is not None
                        and rule.min_airflow_version
                        and profile_version < _version_tuple(rule.min_airflow_version)
                    ):
                        continue
                    if (
                        profile_version is not None
                        and rule.max_airflow_version
                        and profile_version > _version_tuple(rule.max_airflow_version)
                    ):
                        continue
                    replacement = rule.replacement
                else:
                    replacement = rule
                findings.append(
                    _finding(
                        context.policy,
                        model,
                        call.line,
                        FindingStatus.FAIL,
                        f"forbidden operator {resolved}; replacement guidance: {replacement}",
                        f"operator:{resolved}:{call.line}",
                        replacement,
                        fix_payload=RemediationPayload(
                            fix_kind="forbidden-operators",
                            action=RemediationAction.MANUAL,
                            target=fix_target(call.line, resolved, "statement"),
                            value=replacement,
                            hint="not auto-fixable; apply the replacement guidance",
                        ),
                    )
                )
        return findings


class StartDateFreshnessEvaluator:
    """Deterministic check kind: ``start-date-freshness``."""

    policy_id = "AIR-DET-007"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(StartDateFreshnessConfig, context.policy.configuration)
        findings: list[Finding] = []
        current_year = datetime.now(UTC).year
        for model in context.models:
            for dag in model.dags:
                if dag.start_date is None:
                    findings.append(
                        _finding(
                            context.policy,
                            model,
                            dag.line,
                            FindingStatus.FAIL,
                            "start_date is missing or could not be resolved statically; "
                            f"set a recent timezone-aware start_date no older than "
                            f"{configuration.max_age_years} year(s)",
                            f"dag:{dag.variable_name or dag.line}:start_date:missing",
                            fix_payload=RemediationPayload(
                                fix_kind="start-date-freshness",
                                action=RemediationAction.MANUAL,
                                target=fix_target(dag.line, dag.variable_name, "dag-call"),
                                hint="move start_date to a recent timezone-aware date "
                                "(e.g. pendulum.datetime(..., tz='UTC'))",
                            ),
                        )
                    )
                    continue
                year, month, day = dag.start_date
                naive = dag.start_date_tz is False
                stale = (current_year - year) > configuration.max_age_years
                if not stale and not (naive and configuration.require_timezone):
                    continue
                problems: list[str] = []
                if stale:
                    problems.append(
                        f"start_date {year:04d}-{month:02d}-{day:02d} is older than "
                        f"{configuration.max_age_years} year(s)"
                    )
                if naive and configuration.require_timezone:
                    problems.append("start_date has no timezone")
                anchor = f"dag:{dag.variable_name or dag.line}:start_date"
                findings.append(
                    _finding(
                        context.policy,
                        model,
                        dag.line,
                        FindingStatus.FAIL,
                        "; ".join(problems),
                        anchor,
                        fix_payload=RemediationPayload(
                            fix_kind="start-date-freshness",
                            action=RemediationAction.MANUAL,
                            target=fix_target(dag.line, dag.variable_name, "dag-call"),
                            hint="move start_date to a recent timezone-aware date "
                            "(e.g. pendulum.datetime(..., tz='UTC'))",
                        ),
                    )
                )
        return findings


class CatchupPolicyEvaluator:
    """Deterministic check kind: ``catchup-policy``."""

    policy_id = "AIR-DET-008"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(CatchupPolicyConfig, context.policy.configuration)
        findings: list[Finding] = []
        for model in context.models:
            for dag in model.dags:
                if dag.catchup is not True or configuration.allow_catchup:
                    continue
                anchor = f"dag:{dag.variable_name or dag.line}:catchup"
                findings.append(
                    _finding(
                        context.policy,
                        model,
                        dag.line,
                        FindingStatus.FAIL,
                        f"catchup is enabled for {dag.variable_name or 'dag'}; with a stale "
                        "start_date this schedules every missed interval (backfill bomb)",
                        anchor,
                        fix_payload=RemediationPayload(
                            fix_kind="catchup-policy",
                            action=RemediationAction.SET_KWARG,
                            kwarg="catchup",
                            target=fix_target(dag.line, dag.variable_name, "dag-call"),
                            value="False",
                            hint="sets catchup=False on the DAG call",
                        ),
                    )
                )
        return findings


class ModuleScopeVariablesEvaluator:
    """Deterministic check kind: ``module-scope-variables``."""

    policy_id = "AIR-DET-009"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(ModuleScopeVariablesConfig, context.policy.configuration)
        findings: list[Finding] = []
        for model in context.models:
            for call in model.calls:
                if not call.module_scope:
                    continue
                if not any(call.qualified_name == pattern for pattern in configuration.patterns):
                    continue
                anchor = f"call:{call.qualified_name}:{call.line}"
                findings.append(
                    _finding(
                        context.policy,
                        model,
                        call.line,
                        FindingStatus.FAIL,
                        f"top-level {call.qualified_name}() hits the metadata database on every scheduler parse cycle",
                        anchor,
                        fix_payload=RemediationPayload(
                            fix_kind="module-scope-variables",
                            action=RemediationAction.MOVE_STATEMENT,
                            target=fix_target(call.line, call.qualified_name, "statement"),
                            hint="move the variable access into a task body, or use a {{ var.value.* }} Jinja template",
                        ),
                    )
                )
        return findings


class SensitiveLoggingEvaluator:
    """Deterministic check kind: ``sensitive-logging`` (hardcoded secrets)."""

    policy_id = "AIR-DET-010"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(SensitiveLoggingConfig, context.policy.configuration)
        findings: list[Finding] = []
        for model in context.models:
            for constant in model.constants:
                if not isinstance(constant.value, str):
                    continue
                looks_secret = secret_like(constant.name) or any(
                    pattern.lower() in constant.name.lower() for pattern in configuration.secret_patterns
                )
                if not looks_secret:
                    continue
                findings.append(
                    _finding(
                        context.policy,
                        model,
                        constant.line,
                        FindingStatus.FAIL,
                        f"module-scope constant {constant.name!r} looks like a hardcoded credential",
                        anchor=f"secret:{constant.name}:{constant.line}",
                        fix_payload=RemediationPayload(
                            fix_kind="sensitive-logging",
                            action=RemediationAction.MANUAL,
                            target=fix_target(constant.line, constant.name, "statement"),
                            hint="move the value into an Airflow Connection or a secrets "
                            "backend; never commit credentials",
                        ),
                    )
                )
        return findings


class DynamicDagFactoryEvaluator:
    """Deterministic check kind: ``dynamic-dag-factory`` (loop-generated DAGs)."""

    policy_id = "AIR-DET-011"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(DynamicDagFactoryConfig, context.policy.configuration)
        if configuration.allow:
            return []
        findings: list[Finding] = []
        for model in context.models:
            for line in model.dynamic_dag_lines:
                anchor = f"dynamic-dag:{model.source.relative_path}:{line}"
                findings.append(
                    _finding(
                        context.policy,
                        model,
                        line,
                        FindingStatus.FAIL,
                        "module-scope loop generates DAGs; per Airflow best practices "
                        "this slows fleet-wide parsing and multiplies scheduling load",
                        anchor,
                        fix_payload=RemediationPayload(
                            fix_kind="dynamic-dag-factory",
                            action=RemediationAction.MANUAL,
                            target=fix_target(line, None, "statement"),
                            hint="prefer dynamic task mapping, DAG bundles, or config-file "
                            "generation committed to the repo",
                        ),
                    )
                )
        return findings


def _ruff_path(repository_root: Path, filename: object) -> str | None:
    if not isinstance(filename, str) or not filename:
        return None
    path = Path(filename)
    candidate = path if path.is_absolute() else repository_root / path
    try:
        return candidate.resolve().relative_to(repository_root.resolve()).as_posix()
    except (OSError, ValueError):
        return None


def _ruff_rule_matches(code: str, selector: str) -> bool:
    normalized_code = code.upper()
    normalized_selector = selector.upper()
    return normalized_code == normalized_selector or normalized_code.startswith(normalized_selector)


class RuffAirEvaluator:
    """Deterministic check kind: ``ruff-air`` (composed Ruff AIR violations)."""

    policy_id = "AIR-DET-012"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(RuffAirConfig, context.policy.configuration)
        if context.repository_root is None:
            return []
        violations = context.ruff_violations
        if violations is None:
            violations = run_ruff(context.repository_root, configuration.rules) or []
        scanned = {model.source.relative_path for model in context.models}
        findings: list[Finding] = []
        for violation in violations:
            code = violation.get("code")
            if not isinstance(code, str) or not any(
                _ruff_rule_matches(code, selector) for selector in configuration.rules
            ):
                continue
            relative = _ruff_path(context.repository_root, violation.get("filename"))
            if relative is None or relative not in scanned:
                continue
            location = violation.get("location")
            if not isinstance(location, dict):
                continue
            location = cast(dict[str, Any], location)
            row = location.get("row")
            if not isinstance(row, int) or isinstance(row, bool) or row <= 0:
                continue
            raw_message = violation.get("message", "")
            message = raw_message if isinstance(raw_message, str) else str(raw_message)
            detail = f"{code}: {message}"
            findings.append(
                Finding(
                    policy_id=context.policy.id,
                    policy_version=context.policy.version,
                    status=FindingStatus.FAIL,
                    severity=context.policy.severity,
                    enforcement=EnforcementType.DETERMINISTIC,
                    location=FindingLocation(file=Path(relative), start_line=row, end_line=row),
                    evidence=FindingEvidence(text=redact_evidence(detail), start_line=row, end_line=row),
                    explanation=detail,
                    remediation=context.policy.safe_path,
                    fix=RemediationPayload(
                        fix_kind="ruff-air",
                        action=RemediationAction.MANUAL,
                        target=RemediationTarget(line=row, column=0, node="statement"),
                        hint=f"review Ruff rule {code}; source fixes are disabled",
                    ),
                    fingerprint=structural_fingerprint(
                        context.policy, relative, f"ruff:{code}:{row}", FindingStatus.FAIL
                    ),
                )
            )
        return findings


CHECK_EVALUATORS: dict[str, DeterministicEvaluator] = {
    "effective-owner": OwnerEvaluator(),
    "tags": TagEvaluator(),
    "effective-timeout": TimeoutEvaluator(),
    "retry-bounds": RetryEvaluator(),
    "module-scope-io": TopLevelIOEvaluator(),
    "operator-allow-list": ForbiddenOperatorEvaluator(),
    "start-date-freshness": StartDateFreshnessEvaluator(),
    "catchup-policy": CatchupPolicyEvaluator(),
    "module-scope-variables": ModuleScopeVariablesEvaluator(),
    "sensitive-logging": SensitiveLoggingEvaluator(),
    "dynamic-dag-factory": DynamicDagFactoryEvaluator(),
    "ruff-air": RuffAirEvaluator(),
}

LEGACY_POLICY_EVALUATORS: dict[str, DeterministicEvaluator] = {
    "AIR-DET-001": CHECK_EVALUATORS["effective-owner"],
    "AIR-DET-002": CHECK_EVALUATORS["tags"],
    "AIR-DET-003": CHECK_EVALUATORS["effective-timeout"],
    "AIR-DET-004": CHECK_EVALUATORS["retry-bounds"],
    "AIR-DET-005": CHECK_EVALUATORS["module-scope-io"],
    "AIR-DET-006": CHECK_EVALUATORS["operator-allow-list"],
    "AIR-DET-012": CHECK_EVALUATORS["ruff-air"],
}


def _evaluator_for_policy(policy: Policy) -> DeterministicEvaluator | None:
    for check in policy.enforcement.deterministic_checks:
        evaluator = CHECK_EVALUATORS.get(check)
        if evaluator is not None:
            return evaluator
    return LEGACY_POLICY_EVALUATORS.get(policy.id)


def evaluate_deterministic(
    policies: Iterable[Policy],
    models: Sequence[SourceModel],
    airflow_profile: AirflowProfile | None = None,
    repository_root: Path | None = None,
    ruff_violations: list[dict[str, Any]] | None = None,
) -> tuple[list[Finding], list[str], list[str]]:
    """Evaluate supported deterministic policies with stable policy/file ordering."""
    ordered_policies = sorted(policies, key=lambda item: item.id)
    shared_ruff_violations = ruff_violations
    if shared_ruff_violations is None and repository_root is not None:
        ruff_policies = [
            policy
            for policy in ordered_policies
            if policy.status.value == "ACTIVE"
            and policy.enforcement.type in (EnforcementType.DETERMINISTIC, EnforcementType.HYBRID)
            and policy_applies(policy, airflow_profile)
            and ("ruff-air" in policy.enforcement.deterministic_checks or policy.id == "AIR-DET-012")
        ]
        if ruff_policies:
            rules = sorted(
                {rule for policy in ruff_policies for rule in cast(RuffAirConfig, policy.configuration).rules}
            )
            shared_ruff_violations = run_ruff(repository_root, rules) or []
    findings: list[Finding] = []
    evaluated: list[str] = []
    skipped: list[str] = []
    for policy in ordered_policies:
        if policy.status.value != "ACTIVE" or policy.enforcement.type not in (
            EnforcementType.DETERMINISTIC,
            EnforcementType.HYBRID,
        ):
            skipped.append(policy.id)
            continue
        if not policy_applies(policy, airflow_profile):
            skipped.append(policy.id)
            continue
        evaluator = _evaluator_for_policy(policy)
        if evaluator is None:
            skipped.append(policy.id)
            continue
        evaluated.append(policy.id)
        findings.extend(
            evaluator.evaluate(
                EvaluationContext(
                    policy,
                    models,
                    airflow_profile,
                    repository_root,
                    shared_ruff_violations,
                )
            )
        )
    return findings, evaluated, skipped
