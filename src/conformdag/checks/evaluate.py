"""Deterministic policy routing and orchestration."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, cast

from conformdag.analysis import SourceModel
from conformdag.checks.airflow import safety
from conformdag.checks.common import (
    DeterministicEvaluator,
    EvaluationContext,
    EvaluationPhaseError,
    policy_applies,
)
from conformdag.models import AirflowProfile, EnforcementType, Finding, Policy


def _check_registry() -> Any:
    """Return the registry without importing it during evaluator module setup."""
    from conformdag.checks import registry

    return registry


def policy_configuration_issues(policy: Policy) -> list[str]:
    """Return configuration-shape errors before an evaluator can run."""
    if policy.status.value != "ACTIVE":
        return []
    registry = _check_registry()
    checks = policy.enforcement.deterministic_checks
    actual_kind = getattr(policy.configuration, "kind", None)
    issues = [
        f"{policy.id}: deterministic check {check!r} requires configuration kind {expected!r}, got {actual_kind!r}"
        for check in checks
        for expected in [registry.CHECK_CONFIGURATION_KINDS.get(check)]
        if expected is not None and actual_kind != expected
    ]
    if not checks and policy.id in registry.LEGACY_POLICY_CONFIGURATION_KINDS:
        expected = registry.LEGACY_POLICY_CONFIGURATION_KINDS[policy.id]
        if actual_kind != expected:
            issues.append(
                f"{policy.id}: legacy evaluator requires configuration kind {expected!r}, got {actual_kind!r}"
            )
    return issues


def _evaluator_for_policy(policy: Policy) -> DeterministicEvaluator | None:
    registry = _check_registry()
    for check in policy.enforcement.deterministic_checks:
        evaluator = registry.CHECK_EVALUATORS.get(check)
        if evaluator is not None:
            return evaluator
    return registry.LEGACY_POLICY_EVALUATORS.get(policy.id)


def evaluate_deterministic(
    policies: Iterable[Policy],
    models: Sequence[SourceModel],
    airflow_profile: AirflowProfile | None = None,
    repository_root: Path | None = None,
    ruff_violations: list[dict[str, Any]] | None = None,
) -> tuple[list[Finding], list[str], list[str]]:
    """Evaluate supported deterministic policies with stable policy/file ordering."""
    ordered_policies = sorted(policies, key=lambda item: item.id)
    configuration_issues = [issue for policy in ordered_policies for issue in policy_configuration_issues(policy)]
    if configuration_issues:
        raise EvaluationPhaseError("; ".join(configuration_issues))
    shared_ruff_violations = ruff_violations
    if shared_ruff_violations is None and repository_root is not None:
        rules = safety.ruff_rules_for_policies(ordered_policies, airflow_profile)
        if rules:
            shared_ruff_violations = safety.run_ruff(repository_root, rules, [model.source.path for model in models]) or []
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
