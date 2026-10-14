"""Policy and quality-gate authoring validation."""

from __future__ import annotations

from conformdag.models import LifecycleStatus, Policy, PolicyPack, RuffAirConfig


def validate_policy_pack(pack: PolicyPack) -> list[str]:
    """Return registry and quality-gate issues that make a pack unrunnable."""
    from conformdag.checks.registry import CHECK_EVALUATORS
    from conformdag.evaluator import policy_configuration_issues
    from conformdag.gates import validate_quality_gates
    from conformdag.ruff_adapter import validate_ruff_selectors

    issues = validate_quality_gates(pack)
    for policy in pack.policies:
        issues.extend(policy_configuration_issues(policy))
        if isinstance(policy.configuration, RuffAirConfig):
            try:
                validate_ruff_selectors(policy.configuration.rules)
            except ValueError as exc:
                issues.append(f"{policy.id}: {exc}")
        for check in policy.enforcement.deterministic_checks:
            if check not in CHECK_EVALUATORS:
                issues.append(f"{policy.id}: unknown deterministic check {check!r}")
    return issues


def active_policies(pack: PolicyPack) -> list[Policy]:
    """Return only policies that are eligible for evaluation."""
    return [policy for policy in pack.policies if policy.status is LifecycleStatus.ACTIVE]
