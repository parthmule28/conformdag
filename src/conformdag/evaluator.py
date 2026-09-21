"""Compatibility facade for deterministic evaluation.

Introduced in 1.0.0b1 / C05 because existing consumers import evaluator
contracts, classes, and routing from ``conformdag.evaluator``. Remove only
after those imports have an explicit deprecation and compatibility plan.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from conformdag.checks.airflow.metadata import OwnerEvaluator, TagEvaluator
from conformdag.checks.airflow.safety import (
    DynamicDagFactoryEvaluator,
    ForbiddenOperatorEvaluator,
    ModuleScopeVariablesEvaluator,
    RuffAirEvaluator,
    SensitiveLoggingEvaluator,
    TopLevelIOEvaluator,
    _resolve_imported_call,
    _ruff_path,
    _version_tuple,
    ruff_policies_for_scan,
    ruff_rule_matches,
    ruff_rules_for_policies,
    run_ruff,
)
from conformdag.checks.airflow.scheduling import (
    CatchupPolicyEvaluator,
    RetryEvaluator,
    StartDateFreshnessEvaluator,
    TimeoutEvaluator,
    _dag_for_task,
    _effective_value,
)
from conformdag.checks.common import (
    DeterministicEvaluator,
    EvaluationContext,
    EvaluationPhaseError,
    _finding,
    fix_target,
    policy_applies,
    redact_evidence,
    structural_fingerprint,
)
from conformdag.checks.evaluate import (
    _check_registry,
    _evaluator_for_policy,
    evaluate_deterministic,
    policy_configuration_issues,
)

if TYPE_CHECKING:
    from conformdag.checks import registry as _registry_types

    CHECK_CONFIGURATION_KINDS = _registry_types.CHECK_CONFIGURATION_KINDS
    CHECK_EVALUATORS = _registry_types.CHECK_EVALUATORS
    LEGACY_POLICY_CONFIGURATION_KINDS = _registry_types.LEGACY_POLICY_CONFIGURATION_KINDS
    LEGACY_POLICY_EVALUATORS = _registry_types.LEGACY_POLICY_EVALUATORS


_REGISTRY_COMPATIBILITY_NAMES = frozenset(
    {
        "CHECK_CONFIGURATION_KINDS",
        "CHECK_EVALUATORS",
        "LEGACY_POLICY_CONFIGURATION_KINDS",
        "LEGACY_POLICY_EVALUATORS",
    }
)


def __getattr__(name: str) -> Any:
    """Resolve legacy registry views for external imports only."""
    if name not in _REGISTRY_COMPATIBILITY_NAMES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from conformdag.checks import registry

    return getattr(registry, name)
