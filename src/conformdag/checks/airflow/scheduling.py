"""Airflow scheduling deterministic evaluators."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from conformdag.analysis import DagRecord, SourceModel, StaticValue, TaskRecord, ValueState
from conformdag.checks.common import EvaluationContext, finding, fix_target
from conformdag.models import (
    CatchupPolicyConfig,
    ExecutionTimeoutConfig,
    Finding,
    FindingStatus,
    RemediationAction,
    RemediationPayload,
    RetryBoundsConfig,
    StartDateFreshnessConfig,
)


def _dag_for_task(model: SourceModel, task: TaskRecord) -> DagRecord | None:
    if task.dag_line is not None:
        for dag in model.dags:
            if dag.line == task.dag_line:
                return dag
    for dag in model.dags:
        if task.dag_name is None or task.dag_name == dag.variable_name:
            return dag
    return None


def _effective_value(model: SourceModel, task: TaskRecord, name: str) -> StaticValue:
    if name in task.unresolved_kwargs:
        return StaticValue(ValueState.UNRESOLVED)
    if name in task.values:
        return StaticValue(ValueState.RESOLVED, task.values[name])
    dag = _dag_for_task(model, task)
    if dag is None:
        return StaticValue(ValueState.ABSENT)
    if name in dag.unresolved_defaults:
        return StaticValue(ValueState.UNRESOLVED)
    if name in dag.defaults:
        return StaticValue(ValueState.RESOLVED, dag.defaults[name])
    return StaticValue(ValueState.ABSENT)


class TimeoutEvaluator:
    policy_id = "AIR-DET-003"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(ExecutionTimeoutConfig, context.policy.configuration)
        findings: list[Finding] = []
        for model in context.models:
            for task in model.tasks:
                resolved = _effective_value(model, task, "execution_timeout")
                if resolved.state is ValueState.UNRESOLVED:
                    findings.append(
                        finding(
                            context.policy,
                            model,
                            task.line,
                            FindingStatus.ERROR,
                            f"task {task.task_id or task.qualified_name} has an unresolved execution_timeout; "
                            "the effective value cannot be verified statically",
                            f"task:{task.task_id or task.line}:timeout:unresolved",
                        )
                    )
                    continue
                value = resolved.value if resolved.state is ValueState.RESOLVED else None
                if resolved.state is ValueState.ABSENT:
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
                    finding(
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
                retries_value = _effective_value(model, task, "retries")
                delay_value = _effective_value(model, task, "retry_delay")
                unresolved = [
                    name
                    for name, value in (("retries", retries_value), ("retry_delay", delay_value))
                    if value.state is ValueState.UNRESOLVED
                ]
                if unresolved:
                    findings.append(self._unresolved_finding(context, model, task, sorted(unresolved)))
                    continue
                retries = retries_value.value if retries_value.state is ValueState.RESOLVED else 0
                delay = delay_value.value if delay_value.state is ValueState.RESOLVED else 0
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
                    finding(
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
        return finding(
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
                        finding(
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
                    finding(
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
                    finding(
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
